from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any, Protocol, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.gateway import GatewayConfiguration
from coordination.interpretation.projection import (
    EvidenceExcerpt,
    InterpretationProjection,
    MissingDataMarker,
    PermittedEmployee,
    SourceVersionEvidence,
)
from coordination.interpretation.service import InterpretationOutcome, InterpretationRunRecorder

SUPPORTED_CONSTRAINT_TYPES = (
    "acceptance_review",
    "dependency_lag",
    "effort",
    "eligibility",
    "fixed_attendance",
    "requested_deadline",
    "required_input",
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
class PlanningRequestView:
    request_id: UUID
    status: str
    request_version: int
    latest_outcome: str | None
    candidate_digest: str | None
    clarifications: tuple[ClarificationRecord, ...]


@dataclass(frozen=True, slots=True)
class ProjectionBundle:
    projection: InterpretationProjection
    retrieval_run_id: UUID


class InterpretationStore(Protocol):
    def create_request(
        self, *, context: CompanyContext, command: CreatePlanningRequest
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
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                if command.project_id is not None:
                    project = connection.execute(
                        "select id from app.projects where company_id = %s and id = %s for share",
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
                        for share
                        """,
                        (context.company_id, list(command.selected_source_ids)),
                    ).fetchall()
                    if {cast(UUID, row["id"]) for row in source_rows} != set(
                        command.selected_source_ids
                    ):
                        raise PlanningRequestSourceNotFoundError("selected source was not found")

                row = connection.execute(
                    """
                    insert into app.planning_requests (
                      company_id, project_id, requester_membership_id, original_prompt,
                      requested_priority_key, requested_deadline, requested_deadline_timezone,
                      idempotency_key, request_digest
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (company_id, requester_membership_id, idempotency_key)
                    do update set id = app.planning_requests.id
                    where app.planning_requests.request_digest = excluded.request_digest
                    returning id, status, request_version, (xmax = 0) as created
                    """,
                    (
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
                ).fetchone()
                if row is None:
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
            created=cast(bool, row["created"]),
        )

    def get_request(self, *, context: CompanyContext, request_id: UUID) -> PlanningRequestView:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_api",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning-request:read",
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select request.id, request.status, request.request_version,
                           run.outcome as latest_outcome,
                           encode(candidate.contract_digest, 'hex') as candidate_digest,
                           candidate.id as candidate_id
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
        except PlanningRequestNotFoundError:
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error

        return PlanningRequestView(
            request_id=cast(UUID, row["id"]),
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
                    select id, timezone
                    from app.employee_profiles
                    where company_id = %s and status = 'active'
                    order by id
                    """,
                    (context.company_id,),
                ).fetchall()
        except (PlanningRequestNotFoundError, PlanningRequestSourceNotFoundError):
            raise
        except psycopg.Error as error:
            raise InterpretationStoreUnavailableError(
                "interpretation store is unavailable"
            ) from error

        missing_data = [
            MissingDataMarker(
                kind="commitments",
                reason="No task/commitment snapshot exists in this implementation slice.",
                blocking=False,
            ),
            MissingDataMarker(
                kind="capacity",
                reason="Working-rule and availability snapshots are not yet recorded.",
                blocking=False,
            ),
            MissingDataMarker(
                kind="priority_policy",
                reason="Company priority vocabulary has not been configured.",
                blocking=request["requested_priority_key"] is not None,
            ),
        ]
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
                    status="active",
                )
                for row in employee_rows
            ),
            commitments=(),
            capacity=(),
            dependencies=(),
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
                      and status in ('pending_interpretation', 'failed', 'clarification_required')
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
        request_status = "interpreted" if outcome.status == "admitted" else "clarification_required"
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
                for question in contract.clarifications:
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
