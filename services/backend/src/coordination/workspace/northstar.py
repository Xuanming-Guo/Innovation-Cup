"""Canonical scenario intake uses the normal durable interpretation lineage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

import psycopg

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.admission import AdmissionResult
from coordination.interpretation.contracts import CandidateTaskContract
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    PostgresInterpretationStore,
)
from coordination.interpretation.projection import InterpretationProjection
from coordination.interpretation.prompt import (
    FiniteRequirementGuidance,
    InterpretationRepairContext,
    TaskRequirementGuidance,
)
from coordination.planning.materializer import PlanningResourceProfile
from coordination.planning.northstar import (
    NORTHSTAR_INTAKE,
    NORTHSTAR_SCENARIO_VERSION,
    build_northstar_snapshot,
)
from coordination.planning.northstar_authority import (
    NorthstarAuthorityManifest,
    admit_live_northstar_contract,
    build_live_northstar_snapshot,
    canonical_authority_manifest,
)
from coordination.planning.persistence import (
    PlanningPersistenceError,
    PlanningStateConflictError,
    PostgresPlanningLedger,
)
from coordination.workspace.persistence import PostgresWorkspaceStore, WorkspaceInputError


@dataclass(frozen=True, slots=True)
class LiveNorthstarAdmission:
    company_id: UUID
    request_id: UUID
    request_version: int
    authority: NorthstarAuthorityManifest
    source_version_ids: dict[str, UUID]
    source_rows: tuple[dict[str, Any], ...]

    def admit(self, contract: CandidateTaskContract) -> AdmissionResult:
        return admit_live_northstar_contract(
            company_id=self.company_id,
            request_id=self.request_id,
            contract=contract,
            source_version_ids=self.source_version_ids,
            authority=self.authority,
        )

    def with_repair_requirements(
        self,
        context: InterpretationRepairContext,
    ) -> InterpretationRepairContext:
        """Summarize authenticated source authority, not the rejected model's claims."""
        guidance = FiniteRequirementGuidance(
            source_version_id=self.source_version_ids["LAUNCH-07"],
            tasks=tuple(
                TaskRequirementGuidance(
                    task_key=task.task_key,
                    skill_or_qualification_keys=tuple(
                        "northstar." + key for key in task.eligible_person_keys
                    ),
                    review_keys=task.review_task_keys,
                )
                for task in self.authority.tasks
            ),
        )
        return context.model_copy(update={"requirement_authority": guidance})

    def validate_projection(self, projection: InterpretationProjection) -> None:
        if (
            projection.company_id != self.company_id
            or projection.request_id != self.request_id
            or projection.request_version != self.request_version
            or projection.original_request.strip() != NORTHSTAR_INTAKE
        ):
            raise PlanningStateConflictError("live projection differs from its authorized request")
        expected = {row["source_version_id"]: row for row in self.source_rows}
        if len(projection.sources) != 7 or {s.source_version_id for s in projection.sources} != set(
            expected
        ):
            raise PlanningStateConflictError(
                "live projection must contain its exact pinned sources"
            )
        for source in projection.sources:
            row = expected[source.source_version_id]
            if (
                source.source_id != row["source_id"]
                or source.authority_status != "authoritative"
                or source.freshness != "current"
                or source.content_sha256_hex != bytes(row["content_sha256"]).hex()
                or len(source.excerpts) != 1
                or source.excerpts[0].locator != row["locator"]
                or source.excerpts[0].text != row["permitted_text"]
            ):
                raise PlanningStateConflictError(
                    "live projection no longer matches pinned authority"
                )


def _load_live_northstar_authority(
    connection: Any,
    *,
    context: CompanyContext,
    request_id: UUID,
) -> LiveNorthstarAdmission:
    """Called only in a worker transaction carrying the current durable lease."""
    manifest_row = connection.execute(
        "select app.get_demo_scenario_manifest(%s,%s) as value",
        (context.company_id, context.demo_run_id),
    ).fetchone()
    if manifest_row is None or manifest_row["value"] is None:
        raise PlanningStateConflictError("the pinned operator authority manifest is unavailable")
    manifest = manifest_row["value"]
    payload = manifest["manifest_payload"]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != manifest["manifest_digest"]:
        raise PlanningStateConflictError("the immutable operator manifest digest changed")
    source_templates = {item["key"]: item for item in payload["sources"]}
    if len(payload["sources"]) != 7 or set(source_templates) != {
        f"LAUNCH-{i:02}" for i in range(1, 8)
    }:
        raise PlanningStateConflictError("the pinned source pack is not the supported complete set")
    authority = NorthstarAuthorityManifest.model_validate(
        source_templates["LAUNCH-07"]["planning_authority"]
    )
    if authority != canonical_authority_manifest():
        raise PlanningStateConflictError("the pinned authority version is not supported")
    request = connection.execute(
        """
        select request.original_prompt,request.request_version
        from app.planning_requests request join app.demo_runs run
          on run.company_id=request.company_id and run.id=request.demo_run_id
        where request.company_id=%s and request.id=%s and request.demo_run_id=%s
          and run.mode='live' and run.state='active'
        """,
        (context.company_id, request_id, context.demo_run_id),
    ).fetchone()
    if request is None or request["original_prompt"].strip() != NORTHSTAR_INTAKE:
        raise PlanningStateConflictError(
            "additional live scenario requests require explicit typed policy admission"
        )
    sources = connection.execute(
        """
        select source.id as source_id,selected.source_version_id,excerpt.locator,
          version.content_sha256,excerpt.text_sha256,excerpt.permitted_text
        from app.planning_request_sources selected
        join app.source_records source on source.company_id=selected.company_id
          and source.id=selected.source_id
        join app.source_versions version on version.company_id=selected.company_id
          and version.id=selected.source_version_id
        join app.source_excerpts excerpt on excerpt.company_id=selected.company_id
          and excerpt.source_version_id=selected.source_version_id
        where selected.company_id=%s and selected.request_id=%s and source.status='active'
          and source.authority_status='authoritative'
          and source.current_version_id=selected.source_version_id
          and source.demo_run_id=%s
          and (version.expires_at is null or version.expires_at>clock_timestamp())
          and app.can_read_source(app.current_actor_id(),source.company_id,source.id)
        """,
        (context.company_id, request_id, context.demo_run_id),
    ).fetchall()
    if len(sources) != 7 or {row["locator"] for row in sources} != source_templates.keys():
        raise PlanningStateConflictError(
            "live source authority is incomplete, changed or inaccessible"
        )
    for row in sources:
        expected_text = source_templates[row["locator"]]["text"]
        expected_digest = sha256(expected_text.encode()).digest()
        if (
            bytes(row["content_sha256"]) != expected_digest
            or bytes(row["text_sha256"]) != expected_digest
            or row["permitted_text"] != expected_text
        ):
            raise PlanningStateConflictError(
                "selected source differs from its pinned operator authority"
            )
    return LiveNorthstarAdmission(
        company_id=context.company_id,
        request_id=request_id,
        request_version=request["request_version"],
        authority=authority,
        source_version_ids={row["locator"]: row["source_version_id"] for row in sources},
        source_rows=tuple(dict(row) for row in sources),
    )


def load_live_northstar_admission(
    *,
    dsn: str,
    context: CompanyContext,
    projection: InterpretationProjection,
    job_id: UUID,
    lease_token: UUID,
    timeout: int = 5,
) -> LiveNorthstarAdmission:
    """Authenticate finite policy before a live contract can become admitted."""
    if context.demo_run_id is None:
        raise PlanningStateConflictError("live Northstar requires an authorized scenario run")
    try:
        with company_transaction(
            dsn,
            role="coordination_worker",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose="northstar:interpretation-admission",
            connect_timeout_seconds=timeout,
        ) as connection:
            connection.execute(
                "select set_config('app.job_id',%s,true),set_config('app.lease_token',%s,true)",
                (str(job_id), str(lease_token)),
            )
            admission = _load_live_northstar_authority(
                connection,
                context=context,
                request_id=projection.request_id,
            )
            admission.validate_projection(projection)
            return admission
    except (ValueError, KeyError, TypeError) as error:
        raise PlanningStateConflictError("live source policy cannot be authenticated") from error
    except psycopg.Error as error:
        raise PlanningPersistenceError("live source authority context is unavailable") from error


def create_northstar_request(
    *, store: PostgresWorkspaceStore, context: CompanyContext, run_id: UUID, idempotency_key: str
) -> dict[str, Any]:
    if context.demo_run_id != run_id:
        raise WorkspaceInputError("select an owned manager run before starting the launch")
    with store.transaction(context, "northstar:intake") as connection:
        authority = connection.execute(
            "select app.can_manage_planning(%s,app.current_actor_id()) as allowed",
            (context.company_id,),
        ).fetchone()
        if authority is None or not authority["allowed"]:
            raise WorkspaceInputError("select an owned manager run before starting the launch")
        run = connection.execute(
            "select mode from app.demo_runs where company_id=%s and id=%s and state='active'",
            (context.company_id, run_id),
        ).fetchone()
        if run is None:
            raise WorkspaceInputError("the selected scenario run is not active")
        sources = connection.execute(
            """
            select distinct source.id,excerpt.locator from app.source_records source
            join app.source_excerpts excerpt on excerpt.company_id=source.company_id
              and excerpt.source_version_id=source.current_version_id
            where source.company_id=%s and source.demo_run_id=%s and source.status='active'
              and source.authority_status='authoritative' and excerpt.locator=any(%s::text[])
              and app.can_read_source(app.current_actor_id(),source.company_id,source.id)
            """,
            (context.company_id, run_id, [f"LAUNCH-{number:02}" for number in range(1, 8)]),
        ).fetchall()
        if {row["locator"] for row in sources} != {f"LAUNCH-{number:02}" for number in range(1, 8)}:
            raise WorkspaceInputError(
                "the scenario's seven authoritative source records are not available"
            )
        project = connection.execute(
            "select id from app.projects where company_id=%s and demo_run_id=%s "
            "order by created_at,id limit 1",
            (context.company_id, run_id),
        ).fetchone()
    command = CreatePlanningRequest(
        project_id=project["id"] if project else None,
        original_request=NORTHSTAR_INTAKE,
        selected_source_ids=tuple(sorted({row["id"] for row in sources}, key=str)),
        requested_priority_key=None,
        requested_deadline=None,
        requested_deadline_timezone=None,
        idempotency_key=idempotency_key,
    )
    record = PostgresInterpretationStore(
        store.dsn, connect_timeout_seconds=store.timeout
    ).create_request(context=context, command=command)
    return {
        "request_id": str(record.request_id),
        "status": record.status,
        "mode": run["mode"],
        "scenario_version": NORTHSTAR_SCENARIO_VERSION,
    }


def load_run_mode(*, dsn: str, context: CompanyContext, timeout: int = 5) -> str:
    if context.demo_run_id is None:
        return "live"
    with company_transaction(
        dsn,
        role="coordination_worker",
        actor_id=context.actor.user_id,
        company_id=context.company_id,
        demo_run_id=context.demo_run_id,
        demo_actor_session_id=context.demo_actor_session_id,
        purpose="northstar:mode",
        connect_timeout_seconds=timeout,
    ) as connection:
        row = connection.execute(
            "select mode from app.demo_runs where company_id=%s and id=%s and state='active'",
            (context.company_id, context.demo_run_id),
        ).fetchone()
        if row is None:
            raise PlanningStateConflictError(
                "scenario run is absent, archived or no longer authorised"
            )
        # Persisted/API spelling is explicit about the authored D0 case; ledger provenance
        # uses the shorter immutable author_kind defined by the fixed-plan schema.
        return "authored_check" if row["mode"] == "authored_d0_check" else str(row["mode"])


def materialize_northstar_snapshot(
    *, dsn: str, context: CompanyContext, candidate_contract_id: UUID, timeout: int = 5
) -> UUID:
    if context.demo_run_id is None:
        raise PlanningStateConflictError(
            "authored materialisation requires a selected scenario run"
        )
    try:
        with company_transaction(
            dsn,
            role="coordination_worker",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose="northstar:materialize",
            connect_timeout_seconds=timeout,
        ) as connection:
            candidate = connection.execute(
                """
                select candidate.request_id,candidate.created_at,interpretation.model_id,
                       retrieval.projection_digest,
                       app.scope_planning_revision(candidate.company_id,false) as revision
                from app.candidate_contracts candidate
                join app.interpretation_runs interpretation on
                  interpretation.company_id=candidate.company_id
                  and interpretation.id=candidate.interpretation_run_id
                join app.retrieval_runs retrieval on retrieval.company_id=interpretation.company_id
                  and retrieval.id=interpretation.retrieval_run_id
                where candidate.company_id=%s and candidate.id=%s and
                  candidate.admission_status='admitted'
                  and candidate.demo_run_id=%s
                """,
                (context.company_id, candidate_contract_id, context.demo_run_id),
            ).fetchone()
            if (
                candidate is None
                or candidate["model_id"] != "authored:" + NORTHSTAR_SCENARIO_VERSION
            ):
                raise PlanningStateConflictError(
                    "an authored scenario cannot substitute for a live interpretation"
                )
            sources = connection.execute(
                """
                select selected.source_version_id,excerpt.locator from
                  app.planning_request_sources selected
                join app.source_records source on source.company_id=selected.company_id and
                  source.id=selected.source_id
                join app.source_excerpts excerpt on excerpt.company_id=selected.company_id and
                  excerpt.source_version_id=selected.source_version_id
                where selected.company_id=%s and selected.request_id=%s and source.status='active'
                  and source.authority_status='authoritative' and
                    source.current_version_id=selected.source_version_id
                  and app.can_read_source(app.current_actor_id(),source.company_id,source.id)
                """,
                (context.company_id, candidate["request_id"]),
            ).fetchall()
        source_map = {row["locator"]: row["source_version_id"] for row in sources}
        if any(
            key not in source_map for key in ("LAUNCH-02", "LAUNCH-04", "LAUNCH-05", "LAUNCH-07")
        ):
            raise PlanningStateConflictError("the authored scenario source pack is incomplete")
        snapshot = build_northstar_snapshot(
            company_id=context.company_id,
            run_id=context.demo_run_id,
            request_id=candidate["request_id"],
            candidate_contract_id=candidate_contract_id,
            source_version_ids=source_map,
            source_manifest_digest=bytes(candidate["projection_digest"]).hex(),
            base_company_revision=candidate["revision"],
            frozen_at=candidate["created_at"],
        )
        PostgresPlanningLedger(dsn, connect_timeout_seconds=timeout).save_snapshot(
            context=context, snapshot=snapshot
        )
        return snapshot.snapshot_id
    except psycopg.Error as error:
        raise PlanningPersistenceError("authored materialisation context is unavailable") from error


def materialize_live_northstar_snapshot(
    *,
    dsn: str,
    context: CompanyContext,
    candidate_contract_id: UUID,
    job_id: UUID,
    lease_token: UUID,
    timeout: int = 5,
) -> UUID:
    """Live model interpretation plus complete trusted source authority, never P1 replay."""
    if context.demo_run_id is None:
        raise PlanningStateConflictError("live Northstar requires an authorised scenario run")
    try:
        with company_transaction(
            dsn,
            role="coordination_worker",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose="northstar:live-admission",
            connect_timeout_seconds=timeout,
        ) as connection:
            connection.execute(
                "select set_config('app.job_id',%s,true),set_config('app.lease_token',%s,true)",
                (str(job_id), str(lease_token)),
            )
            candidate = connection.execute(
                """
                select candidate.request_id,candidate.contract_json,candidate.created_at,
                  request.original_prompt,interpretation.model_id,retrieval.projection_digest,
                  app.scope_planning_revision(candidate.company_id,false) as revision
                from app.candidate_contracts candidate
                join app.planning_requests request on request.company_id=candidate.company_id
                  and request.id=candidate.request_id
                join app.interpretation_runs interpretation on
                  interpretation.company_id=candidate.company_id
                  and interpretation.id=candidate.interpretation_run_id
                join app.retrieval_runs retrieval on
                  retrieval.company_id=interpretation.company_id
                  and retrieval.id=interpretation.retrieval_run_id
                where candidate.company_id=%s and candidate.id=%s and
                  candidate.admission_status='admitted'
                  and candidate.demo_run_id=%s and request.status='interpreted'
                """,
                (context.company_id, candidate_contract_id, context.demo_run_id),
            ).fetchone()
            if candidate is None or candidate["model_id"].startswith("authored:"):
                raise PlanningStateConflictError(
                    "live admission requires its actual model interpretation"
                )
            admission = _load_live_northstar_authority(
                connection,
                context=context,
                request_id=candidate["request_id"],
            )
            profile_rows = connection.execute(
                """
                select profile.resource_id,profile.timezone,profile.availability_windows,
                  profile.capability_keys,profile.permission_keys,profile.daily_active_minutes,
                  profile.profile_revision,profile.estimate_revision
                from app.planning_resource_profiles profile
                join app.execution_resources resource on resource.company_id=profile.company_id
                  and resource.id=profile.resource_id
                where profile.company_id=%s and profile.active and resource.status='active'
                """,
                (context.company_id,),
            ).fetchall()
            busy_rows = connection.execute(
                """
                select event.employee_id as
                  resource_id,event.start_at,event.end_at,'calendar:'||event.id::text as reference
                from app.calendar_event_versions event
                join app.integration_connections connector on
                  connector.company_id=event.company_id and connector.id=event.connection_id
                where event.company_id=%s and event.status<>'cancelled' and
                  connector.status<>'revoked'
                  and not exists(select 1 from app.calendar_event_versions newer where
                    newer.company_id=event.company_id
                    and newer.connection_id=event.connection_id and
                      newer.external_object_key=event.external_object_key
                    and (newer.created_at,newer.id)>(event.created_at,event.id))
                union all
                select resource_id,start_at,end_at,'committed:'||id::text as reference
                from app.committed_schedule_blocks where company_id=%s and active
                order by resource_id,start_at,end_at,reference
                """,
                (context.company_id, context.company_id),
            ).fetchall()
        profiles = tuple(
            PlanningResourceProfile.model_validate(
                {
                    **{
                        key: value
                        for key, value in dict(row).items()
                        if key != "availability_windows"
                    },
                    "availability": row["availability_windows"],
                }
            )
            for row in profile_rows
        )
        contract = CandidateTaskContract.model_validate(candidate["contract_json"])
        snapshot = build_live_northstar_snapshot(
            company_id=context.company_id,
            run_id=context.demo_run_id,
            request_id=candidate["request_id"],
            candidate_contract_id=candidate_contract_id,
            contract=contract,
            source_version_ids=admission.source_version_ids,
            authority=admission.authority,
            source_manifest_digest=bytes(candidate["projection_digest"]).hex(),
            base_company_revision=candidate["revision"],
            frozen_at=candidate["created_at"],
            profiles=profiles,
            busy_intervals=tuple(
                (row["resource_id"], row["start_at"], row["end_at"], row["reference"])
                for row in busy_rows
            ),
        )
        PostgresPlanningLedger(dsn, connect_timeout_seconds=timeout).save_snapshot(
            context=context, snapshot=snapshot
        )
        return snapshot.snapshot_id
    except (ValueError, KeyError, TypeError) as error:
        raise PlanningStateConflictError(
            "live scenario source policy cannot be admitted completely"
        ) from error
    except psycopg.Error as error:
        raise PlanningPersistenceError("live scenario authority context is unavailable") from error
