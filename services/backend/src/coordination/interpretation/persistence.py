from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any, Protocol, cast
from uuid import UUID, uuid4, uuid5

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.admission import actionable_clarifications
from coordination.interpretation.contracts import safe_planning_model_error_code
from coordination.interpretation.gateway import GatewayConfiguration
from coordination.interpretation.projection import (
    CapacityFact,
    ClarificationAnswer,
    EvidenceExcerpt,
    ExistingCommitment,
    InterpretationProjection,
    MissingDataMarker,
    PermittedEmployee,
    SourceVersionEvidence,
)
from coordination.interpretation.prompt import (
    AUTOMATIC_ADMISSION_REPAIR_CODES,
    InterpretationRepairContext,
    InterpretationRepairIssue,
)
from coordination.interpretation.service import InterpretationOutcome, InterpretationRunRecorder
from coordination.planning.fixed_contracts import MAX_FIXED_PLAN_PROPOSALS

SUPPORTED_CONSTRAINT_TYPES = (
    "acceptance_review",
    "dependency_lag",
    "effort",
    "eligibility",
    "fixed_attendance",
    "requested_deadline",
    "required_input",
)

PLANNING_REQUEST_IDEMPOTENCY_CONSTRAINT = (
    "planning_requests_company_id_requester_membership_id_idempo_key"
)


class InterpretationStoreUnavailableError(RuntimeError):
    """Raised when authoritative interpretation state cannot be accessed safely."""


class PlanningRequestNotFoundError(LookupError):
    """Raised without disclosing whether the request exists in another scope."""


class PlanningRequestSourceNotFoundError(LookupError):
    """Raised when a selected source is absent, stale, or not currently permitted."""


class PlanningRequestIdempotencyConflictError(ValueError):
    """Raised when one idempotency key is reused for different request bytes."""


class InterpretationStateConflictError(ValueError):
    """Raised when the request is already running or has a current admitted candidate."""


class ClarificationStateConflictError(ValueError):
    """Raised when clarification answers target stale or incomplete state."""


class CreatePlanningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID | None
    original_request: str = Field(min_length=1, max_length=8000)
    selected_source_ids: tuple[UUID, ...] = Field(max_length=50)
    requested_priority_key: str | None = Field(max_length=80)
    requested_deadline: datetime | None
    requested_deadline_timezone: str | None = Field(max_length=64)
    idempotency_key: str = Field(min_length=16, max_length=128)

    @model_validator(mode="after")
    def validate_deadline(self) -> CreatePlanningRequest:
        if (self.requested_deadline is None) != (self.requested_deadline_timezone is None):
            raise ValueError("requested deadline and timezone must be supplied together")
        if self.requested_deadline is not None and self.requested_deadline.utcoffset() is None:
            raise ValueError("requested_deadline must include a UTC offset")
        if len(self.selected_source_ids) != len(set(self.selected_source_ids)):
            raise ValueError("selected_source_ids must be unique")
        return self

    @property
    def digest(self) -> bytes:
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"idempotency_key"}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).digest()


class SubmitClarificationAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    request_version: int = Field(gt=0)
    candidate_contract_id: UUID
    answers: dict[str, str] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=16, max_length=128)
    correlation_id: UUID

    @field_validator("answers")
    @classmethod
    def validate_answers(cls, value: dict[str, str]) -> dict[str, str]:
        for key, answer in value.items():
            if (
                not key
                or len(key) > 64
                or not key[0].islower()
                or any(
                    character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in key
                )
            ):
                raise ValueError("clarification answer keys are invalid")
            if not answer.strip() or len(answer.strip()) > 4000:
                raise ValueError("clarification answers must contain 1-4000 characters")
        return {key: answer.strip() for key, answer in value.items()}

    @property
    def digest(self) -> bytes:
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"idempotency_key", "correlation_id"}),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).digest()


@dataclass(frozen=True, slots=True)
class PlanningRequestRecord:
    request_id: UUID
    status: str
    request_version: int
    created: bool


@dataclass(frozen=True, slots=True)
class ClarificationRecord:
    question_key: str
    category: str
    question: str
    blocks_planning: bool
    status: str


@dataclass(frozen=True, slots=True)
class PlanningStageJob:
    job_id: UUID
    state: str
    attempt_count: int
    max_attempts: int
    last_error_code: str | None
    job_kind: str = "planning.run"
    model_call_count: int | None = None
    latest_model_error_code: str | None = None


def _planning_stage_job(row: dict[str, Any], prefix: str) -> PlanningStageJob | None:
    job_id = cast(UUID | None, row[f"{prefix}_id"])
    if job_id is None:
        return None
    return PlanningStageJob(
        job_id=job_id,
        state=cast(str, row[f"{prefix}_state"]),
        attempt_count=cast(int, row[f"{prefix}_attempt_count"]),
        max_attempts=cast(int, row[f"{prefix}_max_attempts"]),
        last_error_code=cast(str | None, row[f"{prefix}_error_code"]),
        job_kind=cast(str, row.get(f"{prefix}_kind", "planning.run")),
        model_call_count=cast(int | None, row.get(f"{prefix}_model_call_count")),
        latest_model_error_code=safe_planning_model_error_code(
            cast(str | None, row.get(f"{prefix}_latest_model_error_code"))
        ),
    )


def _projection_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("projection timestamp is invalid")
    if result.utcoffset() is None:
        raise ValueError("projection timestamp must be timezone-aware")
    return result


@dataclass(frozen=True, slots=True)
class PlanningRequestView:
    request_id: UUID
    status: str
    request_version: int
    latest_outcome: str | None
    candidate_digest: str | None
    clarifications: tuple[ClarificationRecord, ...]
    candidate_contract_id: UUID | None = None
    snapshot_id: UUID | None = None
    plan_id: UUID | None = None
    interpretation_job_state: str | None = None
    materialization_job_state: str | None = None
    planning_job_state: str | None = None
    interpretation_job: PlanningStageJob | None = None
    materialization_job: PlanningStageJob | None = None
    planning_job: PlanningStageJob | None = None
    original_request: str | None = None
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class WorkerPlanningRequestState:
    status: str
    candidate_digest: str | None


@dataclass(frozen=True, slots=True)
class PlanningSourceOption:
    source_id: UUID
    title: str
    classification: str
    source_kind: str


@dataclass(frozen=True, slots=True)
class PlanningRequestSummary:
    request_id: UUID
    original_request: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectionBundle:
    projection: InterpretationProjection
    retrieval_run_id: UUID


class InterpretationStore(Protocol):
    def create_request(
        self, *, context: CompanyContext, command: CreatePlanningRequest
    ) -> PlanningRequestRecord: ...

    def submit_clarification_answers(
        self, *, context: CompanyContext, command: SubmitClarificationAnswers
    ) -> PlanningRequestRecord: ...

    def load_projection(
        self,
        *,
        context: CompanyContext,
        request_id: UUID,
        retrieval_run_id: UUID,
        now: datetime | None = None,
    ) -> ProjectionBundle: ...

    def get_request(self, *, context: CompanyContext, request_id: UUID) -> PlanningRequestView: ...

    def list_planning_context(
        self, *, context: CompanyContext
    ) -> tuple[tuple[PlanningSourceOption, ...], tuple[PlanningRequestSummary, ...]]: ...

    def recorder(
        self,
        *,
        context: CompanyContext,
        request_id: UUID,
        retrieval_run_id: UUID,
    ) -> InterpretationRunRecorder: ...


class PostgresInterpretationStore:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def load_repair_context(
        self,
        *,
        context: CompanyContext,
        request_id: UUID,
    ) -> InterpretationRepairContext | None:
        """Only safe diagnostics from this request's latest immutable rejection.

        No raw model content, issue messages or prior source text enters a repair
        prompt. Current evidence must be retrieved and authorized separately.
        """
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="interpretation:repair-context",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select candidate.contract_digest, candidate.validation_issues
                    from app.candidate_contracts candidate
                    join app.planning_requests request on request.company_id=candidate.company_id
                      and request.id=candidate.request_id
                    where candidate.company_id=%s and candidate.request_id=%s
                      and candidate.demo_run_id is not distinct from %s
                      and request.demo_run_id is not distinct from %s
                      and candidate.admission_status='rejected' and request.status='failed'
                    order by candidate.created_at desc,candidate.id desc limit 1
                    """,
                    (context.company_id, request_id, context.demo_run_id, context.demo_run_id),
                ).fetchone()
            if row is None:
                return None
            issues = row["validation_issues"]
            if not issues or any(
                issue.get("code") not in AUTOMATIC_ADMISSION_REPAIR_CODES
                or issue.get("disposition") != "reject"
                for issue in issues
            ):
                return None
            return InterpretationRepairContext(
                previous_contract_digest=bytes(row["contract_digest"]).hex(),
                issues=tuple(
                    InterpretationRepairIssue(code=issue["code"], path=issue["path"])
                    for issue in issues[:24]
                ),
            )
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError("repair context is unavailable") from error
        except (ValueError, TypeError, KeyError) as error:
            raise InterpretationStateConflictError("repair context cannot be admitted") from error

    def recorder(
        self,
        *,
        context: CompanyContext,
        request_id: UUID,
        retrieval_run_id: UUID,
    ) -> InterpretationRunRecorder:
        return PostgresInterpretationRecorder(
            self._dsn,
            context=context,
            request_id=request_id,
            retrieval_run_id=retrieval_run_id,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def create_request(
        self,
        *,
        context: CompanyContext,
        command: CreatePlanningRequest,
    ) -> PlanningRequestRecord:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:create",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                if command.project_id is not None:
                    project = connection.execute(
                        "select id from app.projects where company_id = %s and id = %s",
                        (context.company_id, command.project_id),
                    ).fetchone()
                    if project is None:
                        raise PlanningRequestNotFoundError("project was not found")

                source_rows: list[dict[str, Any]] = []
                if command.selected_source_ids:
                    source_rows = connection.execute(
                        """
                        select id, current_version_id
                        from app.source_records
                        where company_id = %s
                          and id = any(%s)
                          and status = 'active'
                          and authority_status <> 'revoked'
                          and current_version_id is not null
                        """,
                        (context.company_id, list(command.selected_source_ids)),
                    ).fetchall()
                    if {cast(UUID, row["id"]) for row in source_rows} != set(
                        command.selected_source_ids
                    ):
                        raise PlanningRequestSourceNotFoundError("selected source was not found")

                def load_idempotent_request() -> dict[str, Any] | None:
                    return cast(
                        dict[str, Any] | None,
                        connection.execute(
                            """
                            select id, status, request_version, request_digest
                            from app.planning_requests
                            where company_id = %s
                              and requester_membership_id = %s
                              and idempotency_key = %s
                            """,
                            (
                                context.company_id,
                                context.membership_id,
                                command.idempotency_key,
                            ),
                        ).fetchone(),
                    )

                row = load_idempotent_request()
                created = False
                if row is None:
                    request_id = uuid4()
                    try:
                        # A savepoint keeps a concurrent unique-key race from aborting the
                        # surrounding request transaction. RLS-safe creation uses a plain insert:
                        # PostgreSQL applies SELECT policies to ON CONFLICT target rows.
                        with connection.transaction():
                            connection.execute(
                                """
                                insert into app.planning_requests (
                                  id, company_id, project_id, requester_membership_id,
                                  original_prompt, requested_priority_key, requested_deadline,
                                  requested_deadline_timezone, idempotency_key, request_digest
                                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    request_id,
                                    context.company_id,
                                    command.project_id,
                                    context.membership_id,
                                    command.original_request.strip(),
                                    command.requested_priority_key,
                                    command.requested_deadline,
                                    command.requested_deadline_timezone,
                                    command.idempotency_key,
                                    command.digest,
                                ),
                            )
                    except psycopg.errors.UniqueViolation as error:
                        if error.diag.constraint_name != PLANNING_REQUEST_IDEMPOTENCY_CONSTRAINT:
                            raise
                    else:
                        created = True
                    row = load_idempotent_request()

                if row is None:
                    raise InterpretationStoreUnavailableError(
                        "planning request was not readable after creation"
                    )
                if bytes(row["request_digest"]) != command.digest:
                    raise PlanningRequestIdempotencyConflictError(
                        "idempotency key already identifies a different request"
                    )

                request_id = cast(UUID, row["id"])
                for source in source_rows:
                    connection.execute(
                        """
                        insert into app.planning_request_sources (
                          company_id, request_id, source_id, source_version_id
                        ) values (%s, %s, %s, %s)
                        on conflict (company_id, request_id, source_id) do nothing
                        """,
                        (
                            context.company_id,
                            request_id,
                            source["id"],
                            source["current_version_id"],
                        ),
                    )
        except (
            PlanningRequestIdempotencyConflictError,
            PlanningRequestNotFoundError,
            PlanningRequestSourceNotFoundError,
        ):
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error

        return PlanningRequestRecord(
            request_id=request_id,
            status=cast(str, row["status"]),
            request_version=cast(int, row["request_version"]),
            created=created,
        )

    def submit_clarification_answers(
        self,
        *,
        context: CompanyContext,
        command: SubmitClarificationAnswers,
    ) -> PlanningRequestRecord:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:answer-clarifications",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select * from app.submit_planning_clarifications(
                      %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        command.request_id,
                        command.request_version,
                        command.candidate_contract_id,
                        Jsonb(command.answers),
                        command.idempotency_key,
                        command.digest,
                        command.correlation_id,
                    ),
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise PermissionError("manager authority is required") from error
        except psycopg.errors.UniqueViolation as error:
            raise PlanningRequestIdempotencyConflictError(
                "clarification idempotency key already identifies another command"
            ) from error
        except psycopg.errors.SerializationFailure as error:
            raise ClarificationStateConflictError(
                "clarification target changed before the answer was stored"
            ) from error
        except psycopg.errors.InvalidParameterValue as error:
            message = str(error)
            if "planning_request_not_found" in message:
                raise PlanningRequestNotFoundError("planning request was not found") from error
            raise ClarificationStateConflictError(
                "clarification answers are incomplete or no longer current"
            ) from error
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "clarification answers could not be stored"
            ) from error
        if row is None:
            raise InterpretationStoreUnavailableError(
                "clarification answer command returned no state"
            )
        return PlanningRequestRecord(
            request_id=cast(UUID, row["request_id"]),
            status=cast(str, row["status"]),
            request_version=cast(int, row["request_version"]),
            created=cast(bool, row["created"]),
        )

    def list_planning_context(
        self, *, context: CompanyContext
    ) -> tuple[tuple[PlanningSourceOption, ...], tuple[PlanningRequestSummary, ...]]:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:context",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                source_rows = connection.execute(
                    """
                    select id, coalesce(title, 'Untitled source') as title,
                           classification, source_kind
                    from app.source_records
                    where company_id = %s and status = 'active'
                      and authority_status = 'authoritative'
                      and current_version_id is not null
                    order by title, id
                    """,
                    (context.company_id,),
                ).fetchall()
                request_rows = connection.execute(
                    """
                    select id, original_prompt, status, created_at
                    from app.planning_requests
                    where company_id = %s
                    order by created_at desc, id desc limit 20
                    """,
                    (context.company_id,),
                ).fetchall()
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError("planning context is unavailable") from error
        return (
            tuple(
                PlanningSourceOption(
                    source_id=cast(UUID, row["id"]),
                    title=cast(str, row["title"]),
                    classification=cast(str, row["classification"]),
                    source_kind=cast(str, row["source_kind"]),
                )
                for row in source_rows
            ),
            tuple(
                PlanningRequestSummary(
                    request_id=cast(UUID, row["id"]),
                    original_request=cast(str, row["original_prompt"]),
                    status=cast(str, row["status"]),
                    created_at=cast(datetime, row["created_at"]),
                )
                for row in request_rows
            ),
        )

    def get_request(self, *, context: CompanyContext, request_id: UUID) -> PlanningRequestView:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:read",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select request.id, request.status, request.request_version,
                           request.original_prompt, request.project_id,
                           run.outcome as latest_outcome,
                           encode(candidate.contract_digest, 'hex') as candidate_digest,
                           candidate.id as candidate_id,
                           snapshot.id as snapshot_id,
                           plan.id as plan_id,
                           interpretation_job.state as interpretation_job_state,
                           materialization_job.state as materialization_job_state,
                           planning_job.state as planning_job_state,
                           interpretation_job.id as interpretation_job_id,
                           interpretation_job.job_kind as interpretation_job_kind,
                           interpretation_job.attempt_count as interpretation_job_attempt_count,
                           interpretation_job.max_attempts as interpretation_job_max_attempts,
                           interpretation_job.last_error_code as interpretation_job_error_code,
                           materialization_job.id as materialization_job_id,
                           materialization_job.job_kind as materialization_job_kind,
                           materialization_job.attempt_count as materialization_job_attempt_count,
                           materialization_job.max_attempts as materialization_job_max_attempts,
                           materialization_job.last_error_code as materialization_job_error_code,
                           planning_job.id as planning_job_id,
                           planning_job.job_kind as planning_job_kind,
                           planning_job.attempt_count as planning_job_attempt_count,
                           planning_job.max_attempts as planning_job_max_attempts,
                           planning_job.last_error_code as planning_job_error_code
                    from app.planning_requests as request
                    left join lateral (
                      select interpretation.id, interpretation.outcome
                      from app.interpretation_runs as interpretation
                      where interpretation.company_id = request.company_id
                        and interpretation.request_id = request.id
                      order by interpretation.started_at desc, interpretation.id desc
                      limit 1
                    ) as run on true
                    left join app.candidate_contracts as candidate
                      on candidate.company_id = request.company_id
                     and candidate.interpretation_run_id = run.id
                    left join lateral (
                      select value.id
                      from app.planning_snapshots as value
                      where value.company_id = request.company_id
                        and value.candidate_contract_id = candidate.id
                      order by value.frozen_at desc, value.id desc limit 1
                    ) as snapshot on true
                    left join lateral (
                      select value.id
                      from app.plans as value
                      where value.company_id = request.company_id
                        and value.snapshot_id = snapshot.id
                      order by value.created_at desc, value.id desc limit 1
                    ) as plan on true
                    left join app.durable_jobs as interpretation_job
                      on interpretation_job.company_id = request.company_id
                     and interpretation_job.job_kind = 'interpretation.run'
                     and interpretation_job.aggregate_id = request.id
                    left join app.durable_jobs as materialization_job
                      on materialization_job.company_id = request.company_id
                     and materialization_job.job_kind = 'planning.materialize'
                     and materialization_job.aggregate_id = candidate.id
                    left join lateral (
                      select value.* from app.durable_jobs as value
                      where value.company_id = request.company_id
                        and value.job_kind in ('plan.propose', 'planning.run')
                        and value.aggregate_id = snapshot.id
                      order by (value.job_kind = 'plan.propose') desc,
                        value.created_at desc, value.id desc limit 1
                    ) as planning_job on true
                    where request.company_id = %s and request.id = %s
                    """,
                    (context.company_id, request_id),
                ).fetchone()
                if row is None:
                    raise PlanningRequestNotFoundError("planning request was not found")
                question_rows: list[dict[str, Any]] = []
                if row["candidate_id"] is not None:
                    question_rows = connection.execute(
                        """
                        select question_key, category, question, blocks_planning, status
                        from app.clarification_questions
                        where company_id = %s and candidate_contract_id = %s
                        order by created_at, question_key
                        """,
                        (context.company_id, row["candidate_id"]),
                    ).fetchall()
                if row.get("planning_job_kind") == "plan.propose" and row["planning_job_id"]:
                    # Match only this durable workflow's bounded authoring attempts.
                    # A request can also have interpretation, assistant or older
                    # snapshot runs; those must not inflate planning progress.
                    model_ids = [
                        uuid5(row["planning_job_id"], f"author:{round_index}:attempt:{attempt}")
                        for round_index in range(1, MAX_FIXED_PLAN_PROPOSALS + 1)
                        for attempt in range(1, 21)
                    ]
                    model_rows = connection.execute(
                        """
                        select model.status, model.error_code
                        from app.model_runs as model
                        where model.company_id = %s and model.request_id = %s
                          and model.demo_run_id is not distinct from %s
                          and model.id = any(%s::uuid[])
                          and model.stage in ('plan.propose', 'plan.revise')
                        order by model.started_at desc, model.id desc
                        """,
                        (context.company_id, request_id, context.demo_run_id, model_ids),
                    ).fetchall()
                    row["planning_job_model_call_count"] = len(model_rows)
                    row["planning_job_latest_model_error_code"] = (
                        safe_planning_model_error_code(model_rows[0]["error_code"])
                        if model_rows and model_rows[0]["status"] == "failed"
                        else None
                    )
        except PlanningRequestNotFoundError:
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error

        return PlanningRequestView(
            request_id=cast(UUID, row["id"]),
            original_request=cast(str, row["original_prompt"]),
            project_id=cast(UUID | None, row["project_id"]),
            status=cast(str, row["status"]),
            request_version=cast(int, row["request_version"]),
            latest_outcome=cast(str | None, row["latest_outcome"]),
            candidate_digest=cast(str | None, row["candidate_digest"]),
            clarifications=tuple(
                ClarificationRecord(
                    question_key=cast(str, question["question_key"]),
                    category=cast(str, question["category"]),
                    question=cast(str, question["question"]),
                    blocks_planning=cast(bool, question["blocks_planning"]),
                    status=cast(str, question["status"]),
                )
                for question in question_rows
            ),
            candidate_contract_id=cast(UUID | None, row["candidate_id"]),
            snapshot_id=cast(UUID | None, row["snapshot_id"]),
            plan_id=cast(UUID | None, row["plan_id"]),
            interpretation_job_state=cast(str | None, row["interpretation_job_state"]),
            materialization_job_state=cast(str | None, row["materialization_job_state"]),
            planning_job_state=cast(str | None, row["planning_job_state"]),
            interpretation_job=_planning_stage_job(row, "interpretation_job"),
            materialization_job=_planning_stage_job(row, "materialization_job"),
            planning_job=_planning_stage_job(row, "planning_job"),
        )

    def get_worker_request_state(
        self, *, context: CompanyContext, request_id: UUID
    ) -> WorkerPlanningRequestState:
        """Read only the reconciliation state needed by an interpretation worker."""

        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:worker-reconcile",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select request.status,
                           latest_candidate.candidate_digest
                    from app.planning_requests as request
                    left join lateral (
                      select encode(candidate.contract_digest, 'hex') as candidate_digest
                      from app.interpretation_runs as interpretation
                      join app.candidate_contracts as candidate
                        on candidate.company_id = interpretation.company_id
                       and candidate.interpretation_run_id = interpretation.id
                      where interpretation.company_id = request.company_id
                        and interpretation.request_id = request.id
                      order by interpretation.started_at desc, interpretation.id desc
                      limit 1
                    ) as latest_candidate on true
                    where request.company_id = %s and request.id = %s
                    """,
                    (context.company_id, request_id),
                ).fetchone()
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error
        if row is None:
            raise PlanningRequestNotFoundError("planning request was not found")
        return WorkerPlanningRequestState(
            status=cast(str, row["status"]),
            candidate_digest=cast(str | None, row["candidate_digest"]),
        )

    def load_projection(
        self,
        *,
        context: CompanyContext,
        request_id: UUID,
        retrieval_run_id: UUID,
        now: datetime | None = None,
    ) -> ProjectionBundle:
        retrieved_at = now or datetime.now(UTC)
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="interpretation:retrieve",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                request = connection.execute(
                    """
                    select id, original_prompt, requested_priority_key, requested_deadline,
                           requested_deadline_timezone, request_version
                    from app.planning_requests
                    where company_id = %s and id = %s
                    for share
                    """,
                    (context.company_id, request_id),
                ).fetchone()
                if request is None:
                    raise PlanningRequestNotFoundError("planning request was not found")

                source_rows = connection.execute(
                    """
                    select selected.source_id, selected.source_version_id, source.source_kind,
                           source.authority_status, source.classification, version.retrieved_at,
                           version.expires_at,
                           encode(version.content_sha256, 'hex') as content_sha256_hex
                    from app.planning_request_sources as selected
                    join app.source_records as source
                      on source.company_id = selected.company_id
                     and source.id = selected.source_id
                    join app.source_versions as version
                      on version.company_id = selected.company_id
                     and version.id = selected.source_version_id
                    where selected.company_id = %s and selected.request_id = %s
                      and source.status = 'active'
                      and source.authority_status in ('authoritative', 'unverified')
                    order by selected.source_id
                    """,
                    (context.company_id, request_id),
                ).fetchall()
                expected_source_count = connection.execute(
                    """
                    select count(*)::integer as count
                    from app.planning_request_sources
                    where company_id = %s and request_id = %s
                    """,
                    (context.company_id, request_id),
                ).fetchone()
                if (
                    expected_source_count is None
                    or len(source_rows) != expected_source_count["count"]
                ):
                    raise PlanningRequestSourceNotFoundError(
                        "selected source access changed before interpretation"
                    )

                version_ids = [row["source_version_id"] for row in source_rows]
                excerpts = connection.execute(
                    """
                    select source_version_id, locator, permitted_text
                    from app.source_excerpts
                    where company_id = %s and source_version_id = any(%s)
                    order by source_version_id, locator
                    """,
                    (context.company_id, version_ids or [UUID(int=0)]),
                ).fetchall()
                excerpts_by_version: dict[UUID, list[EvidenceExcerpt]] = {}
                for excerpt in excerpts:
                    version_id = cast(UUID, excerpt["source_version_id"])
                    excerpts_by_version.setdefault(version_id, []).append(
                        EvidenceExcerpt(
                            locator=cast(str, excerpt["locator"]),
                            text=cast(str, excerpt["permitted_text"]),
                        )
                    )

                employee_rows = connection.execute(
                    """
                    select employee.id, profile.timezone,
                           profile.capability_keys, profile.permission_keys,
                           profile.availability_windows, profile.daily_active_minutes
                    from app.employee_profiles as employee
                    join app.execution_resources as resource
                      on resource.company_id = employee.company_id
                     and resource.employee_id = employee.id
                     and resource.status = 'active'
                    join app.planning_resource_profiles as profile
                      on profile.company_id = resource.company_id
                     and profile.resource_id = resource.id
                     and profile.active
                    where employee.company_id = %s and employee.status = 'active'
                    order by employee.id
                    """,
                    (context.company_id,),
                ).fetchall()
                commitment_rows = connection.execute(
                    """
                    select block.id, resource.employee_id, block.start_at, block.end_at,
                           greatest(0, extract(epoch from (block.end_at - block.start_at))
                             / 60)::integer as active_minutes,
                           case when block.exclusive then 'fixed' else 'protected' end as movement
                    from app.committed_schedule_blocks as block
                    join app.execution_resources as resource
                      on resource.company_id = block.company_id
                     and resource.id = block.resource_id
                    where block.company_id = %s and block.active
                      and resource.employee_id is not null
                      and block.end_at > %s
                    order by block.start_at, block.id
                    """,
                    (context.company_id, retrieved_at),
                ).fetchall()
                answer_rows = connection.execute(
                    """
                    with recursive lineage as (
                      select request.id, request.clarification_parent_request_id
                      from app.planning_requests as request
                      where request.company_id = %s and request.id = %s
                      union all
                      select parent.id, parent.clarification_parent_request_id
                      from app.planning_requests as parent
                      join lineage as child
                        on child.clarification_parent_request_id = parent.id
                      where parent.company_id = %s
                    )
                    select response.id as response_id, question.question_key,
                           question.category, question.question, response.answer,
                           response.created_at as answered_at,
                           submission.authority_role
                    from lineage
                    join app.clarification_answer_submissions as submission
                      on submission.company_id = %s
                     and submission.derived_request_id = lineage.id
                    join app.clarification_responses as response
                      on response.company_id = submission.company_id
                     and response.submission_id = submission.id
                    join app.clarification_questions as question
                      on question.company_id = response.company_id
                     and question.id = response.clarification_question_id
                    order by response.created_at, response.id
                    """,
                    (
                        context.company_id,
                        request_id,
                        context.company_id,
                        context.company_id,
                    ),
                ).fetchall()
        except (PlanningRequestNotFoundError, PlanningRequestSourceNotFoundError):
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error

        capacity: list[CapacityFact] = []
        for row in employee_rows:
            for window in cast(list[dict[str, object]], row["availability_windows"]):
                start_at = _projection_datetime(window["start_at"])
                end_at = _projection_datetime(window["end_at"])
                available_minutes = max(
                    0,
                    min(
                        int((end_at - start_at).total_seconds() // 60),
                        cast(int, row["daily_active_minutes"]),
                    ),
                )
                capacity.append(
                    CapacityFact(
                        employee_id=cast(UUID, row["id"]),
                        horizon_start=start_at,
                        horizon_end=end_at,
                        available_active_minutes=available_minutes,
                        source="availability_snapshot",
                    )
                )

        missing_data = [
            MissingDataMarker(
                kind="priority_policy",
                reason="Company priority vocabulary has not been configured.",
                blocking=request["requested_priority_key"] is not None,
            ),
        ]
        if not capacity:
            missing_data.append(
                MissingDataMarker(
                    kind="capacity",
                    reason="No current working-rule or availability snapshot is recorded.",
                    blocking=True,
                )
            )
        if any(
            not excerpts_by_version.get(cast(UUID, row["source_version_id"])) for row in source_rows
        ):
            missing_data.append(
                MissingDataMarker(
                    kind="source_content",
                    reason="One or more selected sources has no permitted extracted excerpt.",
                    blocking=True,
                )
            )

        projection = InterpretationProjection(
            projection_version="interpretation-projection.v1",
            company_id=context.company_id,
            request_id=request_id,
            request_version=cast(int, request["request_version"]),
            original_request=cast(str, request["original_prompt"]),
            retrieved_at=retrieved_at,
            requested_priority_key=cast(str | None, request["requested_priority_key"]),
            requested_deadline=cast(datetime | None, request["requested_deadline"]),
            requested_deadline_timezone=cast(str | None, request["requested_deadline_timezone"]),
            sources=tuple(
                SourceVersionEvidence(
                    source_id=cast(UUID, row["source_id"]),
                    source_version_id=cast(UUID, row["source_version_id"]),
                    source_kind=cast(Any, row["source_kind"]),
                    authority_status=cast(Any, row["authority_status"]),
                    classification=cast(Any, row["classification"]),
                    retrieved_at=cast(datetime, row["retrieved_at"]),
                    expires_at=cast(datetime | None, row["expires_at"]),
                    freshness=(
                        "stale"
                        if row["expires_at"] is not None and row["expires_at"] <= retrieved_at
                        else "current"
                    ),
                    content_sha256_hex=cast(str, row["content_sha256_hex"]),
                    excerpts=tuple(
                        excerpts_by_version.get(cast(UUID, row["source_version_id"]), [])
                    ),
                )
                for row in source_rows
            ),
            employees=tuple(
                PermittedEmployee(
                    employee_id=cast(UUID, row["id"]),
                    timezone=cast(str, row["timezone"]),
                    capability_keys=tuple(sorted(cast(list[str], row["capability_keys"]))),
                    permission_keys=tuple(sorted(cast(list[str], row["permission_keys"]))),
                    status="active",
                )
                for row in employee_rows
            ),
            commitments=tuple(
                ExistingCommitment(
                    commitment_id=cast(UUID, row["id"]),
                    employee_id=cast(UUID, row["employee_id"]),
                    start_at=cast(datetime, row["start_at"]),
                    end_at=cast(datetime, row["end_at"]),
                    active_minutes=cast(int, row["active_minutes"]),
                    movement=cast(Any, row["movement"]),
                )
                for row in commitment_rows
            ),
            capacity=tuple(capacity),
            dependencies=(),
            clarification_answers=tuple(
                ClarificationAnswer(
                    response_id=cast(UUID, row["response_id"]),
                    question_key=cast(str, row["question_key"]),
                    category=cast(Any, row["category"]),
                    question=cast(str, row["question"]),
                    answer=cast(str, row["answer"]),
                    answered_at=cast(datetime, row["answered_at"]),
                    authority_role=cast(Any, row["authority_role"]),
                )
                for row in answer_rows
            ),
            supported_constraint_types=SUPPORTED_CONSTRAINT_TYPES,
            missing_data=tuple(missing_data),
        )
        return ProjectionBundle(projection=projection, retrieval_run_id=retrieval_run_id)


class PostgresInterpretationRecorder(InterpretationRunRecorder):
    def __init__(
        self,
        dsn: str,
        *,
        context: CompanyContext,
        request_id: UUID,
        retrieval_run_id: UUID,
        connect_timeout_seconds: int = 5,
    ) -> None:
        self._dsn = dsn
        self._context = context
        self._request_id = request_id
        self._retrieval_run_id = retrieval_run_id
        self._connect_timeout_seconds = connect_timeout_seconds

    def _transaction(self, purpose: str) -> Any:
        return company_transaction(
            self._dsn,
            role="coordination_worker",
            actor_id=self._context.actor.user_id,
            company_id=self._context.company_id,
            purpose=purpose,
            demo_run_id=self._context.demo_run_id,
            demo_actor_session_id=self._context.demo_actor_session_id,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def start(
        self,
        *,
        run_id: UUID,
        projection: InterpretationProjection,
        configuration: GatewayConfiguration,
        started_at: datetime,
    ) -> None:
        selected_manifest = [
            {
                "authority_status": source.authority_status,
                "classification": source.classification,
                "source_id": str(source.source_id),
                "source_version_id": str(source.source_version_id),
            }
            for source in projection.sources
        ]
        try:
            with self._transaction("interpretation:start") as connection:
                # A provider call is side-effect free. If the preceding durable attempt lost
                # database availability while recording its result, close that stranded run
                # before the next fenced attempt starts instead of retrying forever against an
                # `interpretation_running` request.
                connection.execute(
                    """
                    update app.interpretation_runs
                    set status = 'failed', outcome = 'transient_failure',
                        error_code = 'superseded_by_retry', completed_at = %s
                    where company_id = %s and request_id = %s and status = 'running'
                    """,
                    (started_at, self._context.company_id, self._request_id),
                )
                connection.execute(
                    """
                    insert into app.retrieval_runs (
                      id, company_id, request_id, actor_membership_id, purpose,
                      allowed_scope, selected_manifest, omitted_manifest, missing_manifest,
                      projection_digest, projection_characters, status, started_at, completed_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'complete', %s, %s)
                    """,
                    (
                        self._retrieval_run_id,
                        self._context.company_id,
                        self._request_id,
                        self._context.membership_id,
                        "planning-interpretation",
                        Jsonb(
                            {
                                "company_id": str(self._context.company_id),
                                "request_id": str(self._request_id),
                            }
                        ),
                        Jsonb(selected_manifest),
                        Jsonb([]),
                        Jsonb(
                            [marker.model_dump(mode="json") for marker in projection.missing_data]
                        ),
                        bytes.fromhex(projection.digest),
                        len(projection.canonical_json()),
                        started_at,
                        started_at,
                    ),
                )
                connection.execute(
                    """
                    insert into app.interpretation_runs (
                      id, company_id, request_id, retrieval_run_id, model_id, sdk_version,
                      prompt_version, schema_version, safety_profile, configuration,
                      status, started_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'running', %s)
                    """,
                    (
                        run_id,
                        self._context.company_id,
                        self._request_id,
                        self._retrieval_run_id,
                        configuration.model,
                        version("google-genai"),
                        configuration.prompt_version,
                        configuration.schema_version,
                        configuration.safety_profile,
                        Jsonb(configuration.ledger_values()),
                        started_at,
                    ),
                )
                claimed = connection.execute(
                    """
                    update app.planning_requests
                    set status = 'interpretation_running'
                    where company_id = %s and id = %s
                      and status in (
                        'pending_interpretation', 'failed', 'clarification_required',
                        'interpretation_running'
                      )
                    returning id
                    """,
                    (self._context.company_id, self._request_id),
                ).fetchone()
                if claimed is None:
                    raise InterpretationStateConflictError(
                        "planning request is already running or interpreted"
                    )
        except InterpretationStateConflictError:
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation run could not be started"
            ) from error

    def complete(self, outcome: InterpretationOutcome, *, completed_at: datetime) -> None:
        contract = outcome.response.contract
        request_status = {
            "admitted": "interpreted",
            "clarification_required": "clarification_required",
            "rejected": "failed",
        }[outcome.status]
        try:
            with self._transaction("interpretation:complete") as connection:
                connection.execute(
                    """
                    update app.interpretation_runs
                    set model_version = %s, status = 'completed', outcome = %s,
                        latency_ms = %s, prompt_tokens = %s, candidate_tokens = %s,
                        total_tokens = %s, thought_tokens = %s, provider_response_id = %s,
                        finish_reason = %s, completed_at = %s
                    where company_id = %s and id = %s and status = 'running'
                    """,
                    (
                        outcome.response.model_version,
                        outcome.status,
                        outcome.latency_ms,
                        outcome.response.usage.prompt_tokens,
                        outcome.response.usage.candidate_tokens,
                        outcome.response.usage.total_tokens,
                        outcome.response.usage.thought_tokens,
                        outcome.response.provider_response_id,
                        outcome.response.finish_reason,
                        completed_at,
                        self._context.company_id,
                        outcome.run_id,
                    ),
                )
                candidate = connection.execute(
                    """
                    insert into app.candidate_contracts (
                      company_id, request_id, interpretation_run_id, contract_json,
                      contract_digest, admission_status, validation_issues
                    ) values (%s, %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (
                        self._context.company_id,
                        self._request_id,
                        outcome.run_id,
                        Jsonb(contract.model_dump(mode="json")),
                        bytes.fromhex(outcome.contract_digest),
                        outcome.status,
                        Jsonb(
                            [issue.model_dump(mode="json") for issue in outcome.admission.issues]
                        ),
                    ),
                ).fetchone()
                if candidate is None:
                    raise InterpretationStoreUnavailableError("candidate contract was not stored")
                for question in actionable_clarifications(contract, outcome.admission):
                    connection.execute(
                        """
                        insert into app.clarification_questions (
                          company_id, request_id, candidate_contract_id, question_key,
                          category, question, blocks_planning, related_task_keys
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            self._context.company_id,
                            self._request_id,
                            candidate["id"],
                            question.question_key,
                            question.category,
                            question.question,
                            question.blocks_planning,
                            Jsonb(list(question.related_task_keys)),
                        ),
                    )
                connection.execute(
                    """
                    insert into app.trace_steps (
                      company_id, request_id, retrieval_run_id, interpretation_run_id,
                      step_type, input_digest, output_digest, tool_version, status,
                      viewer_safe_projection
                    ) values (%s, %s, %s, %s, 'candidate_validated', %s, %s, %s, 'complete', %s)
                    """,
                    (
                        self._context.company_id,
                        self._request_id,
                        self._retrieval_run_id,
                        outcome.run_id,
                        bytes.fromhex(outcome.projection_digest),
                        bytes.fromhex(outcome.contract_digest),
                        "coordination-admission/candidate-task-contract.v1",
                        Jsonb(
                            {
                                "admission_status": outcome.status,
                                "issue_codes": [issue.code for issue in outcome.admission.issues],
                            }
                        ),
                    ),
                )
                connection.execute(
                    """
                    update app.planning_requests
                    set status = %s
                    where company_id = %s and id = %s
                    """,
                    (request_status, self._context.company_id, self._request_id),
                )
        except InterpretationStoreUnavailableError:
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation result could not be stored"
            ) from error

    def fail(
        self,
        *,
        run_id: UUID,
        outcome: str,
        error_code: str,
        latency_ms: int,
        completed_at: datetime,
    ) -> None:
        try:
            with self._transaction("interpretation:fail") as connection:
                connection.execute(
                    """
                    update app.interpretation_runs
                    set status = 'failed', outcome = %s, error_code = %s,
                        latency_ms = %s, completed_at = %s
                    where company_id = %s and id = %s and status = 'running'
                    """,
                    (
                        outcome,
                        error_code,
                        latency_ms,
                        completed_at,
                        self._context.company_id,
                        run_id,
                    ),
                )
                connection.execute(
                    """
                    update app.planning_requests
                    set status = 'failed'
                    where company_id = %s and id = %s
                    """,
                    (self._context.company_id, self._request_id),
                )
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation failure could not be stored"
            ) from error
