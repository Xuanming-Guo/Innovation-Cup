from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.interpretation.contracts import CandidateTaskContract
from coordination.planning.contracts import (
    PlanningDecision,
    PlanningSnapshot,
    canonical_digest,
)


class PlanningPersistenceError(RuntimeError):
    """Raised when the planning ledger cannot be accessed safely."""


class PlanningStateConflictError(ValueError):
    """Raised when an artifact conflicts with current authoritative state."""


EMPLOYEE_BRIEF_VERSION_CONSTRAINT = "employee_brief_versions_company_id_plan_id_version_key"


class PlanningLedger(Protocol):
    def load_snapshot(self, *, context: CompanyContext, snapshot_id: UUID) -> PlanningSnapshot: ...

    def save_snapshot(self, *, context: CompanyContext, snapshot: PlanningSnapshot) -> None: ...

    def save_decision(
        self,
        *,
        context: CompanyContext,
        snapshot: PlanningSnapshot,
        decision: PlanningDecision,
    ) -> UUID | None: ...


class PostgresPlanningLedger:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def load_snapshot(self, *, context: CompanyContext, snapshot_id: UUID) -> PlanningSnapshot:
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning:load-snapshot",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                row = connection.execute(
                    """
                    select normalized_snapshot, snapshot_digest
                    from app.planning_snapshots
                    where company_id = %s and id = %s
                    """,
                    (context.company_id, snapshot_id),
                ).fetchone()
        except psycopg.Error as error:
            raise PlanningPersistenceError("planning snapshot could not be loaded") from error
        if row is None:
            raise PlanningStateConflictError("planning snapshot is absent or unreadable")
        try:
            snapshot = PlanningSnapshot.model_validate(row["normalized_snapshot"])
        except ValueError as error:
            raise PlanningStateConflictError("stored planning snapshot is invalid") from error
        if (
            snapshot.snapshot_id != snapshot_id
            or snapshot.company_id != context.company_id
            or bytes(row["snapshot_digest"]).hex() != snapshot.snapshot_digest
        ):
            raise PlanningStateConflictError("stored planning snapshot binding changed")
        return snapshot

    def save_snapshot(self, *, context: CompanyContext, snapshot: PlanningSnapshot) -> None:
        if context.company_id != snapshot.company_id:
            raise PlanningStateConflictError("snapshot company does not match current context")
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning:snapshot",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                current = connection.execute(
                    """
                    select candidate.id, candidate.request_id, candidate.interpretation_run_id,
                           app.scope_planning_revision(company.id,false) as planning_revision,
                             retrieval.projection_digest
                    from app.candidate_contracts as candidate
                    join app.interpretation_runs as interpretation
                      on interpretation.company_id = candidate.company_id
                     and interpretation.id = candidate.interpretation_run_id
                    join app.retrieval_runs as retrieval
                      on retrieval.company_id = interpretation.company_id
                     and retrieval.id = interpretation.retrieval_run_id
                    join app.companies as company on company.id = candidate.company_id
                    where candidate.company_id = %s
                      and candidate.id = %s
                      and candidate.admission_status = 'admitted'
                    """,
                    (context.company_id, snapshot.candidate_contract_id),
                ).fetchone()
                if current is None or current["request_id"] != snapshot.request_id:
                    raise PlanningStateConflictError(
                        "admitted candidate is not current or permitted"
                    )
                if current["planning_revision"] != snapshot.base_company_revision:
                    raise PlanningStateConflictError("snapshot base company revision is stale")
                if bytes(current["projection_digest"]) != bytes.fromhex(
                    snapshot.source_manifest_digest
                ):
                    raise PlanningStateConflictError(
                        "snapshot source manifest does not match the admitted projection"
                    )

                constraint_ids: list[UUID] = []
                for constraint in snapshot.constraints:
                    record_id = uuid5(snapshot.candidate_contract_id, constraint.constraint_id)
                    constraint_json = constraint.model_dump(mode="json")
                    constraint_digest = bytes.fromhex(canonical_digest(constraint_json))
                    connection.execute(
                        """
                        insert into app.validated_constraints (
                          id, company_id, request_id, candidate_contract_id, constraint_key,
                          schema_version, strength, payload, source_version_ids, authority_refs,
                          confidentiality, negotiability, confirmation, constraint_digest
                        ) values (
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) on conflict (company_id, candidate_contract_id, constraint_key) do nothing
                        """,
                        (
                            record_id,
                            context.company_id,
                            snapshot.request_id,
                            snapshot.candidate_contract_id,
                            constraint.constraint_id,
                            constraint.schema_version,
                            constraint.strength,
                            Jsonb(constraint.payload.model_dump(mode="json")),
                            Jsonb([str(value) for value in constraint.source_version_ids]),
                            Jsonb(list(constraint.authority_refs)),
                            constraint.confidentiality,
                            constraint.negotiability,
                            constraint.confirmation,
                            constraint_digest,
                        ),
                    )
                    existing = connection.execute(
                        """
                        select id, constraint_digest
                        from app.validated_constraints
                        where company_id = %s
                          and candidate_contract_id = %s
                          and constraint_key = %s
                        """,
                        (
                            context.company_id,
                            snapshot.candidate_contract_id,
                            constraint.constraint_id,
                        ),
                    ).fetchone()
                    if (
                        existing is None
                        or bytes(existing["constraint_digest"]) != constraint_digest
                    ):
                        raise PlanningStateConflictError(
                            "constraint key already identifies different canonical contents"
                        )
                    stored_constraint_id = cast(UUID, existing["id"])
                    constraint_ids.append(stored_constraint_id)
                    for source_version_id in constraint.source_version_ids:
                        permitted = connection.execute(
                            """
                            select 1
                            from app.planning_request_sources as selected
                            join app.source_records as source
                              on source.company_id = selected.company_id
                             and source.id = selected.source_id
                            join app.source_versions as version
                              on version.company_id = selected.company_id
                             and version.id = selected.source_version_id
                            where selected.company_id = %s
                              and selected.request_id = %s
                              and selected.source_version_id = %s
                              and source.status = 'active'
                              and source.authority_status = 'authoritative'
                              and source.current_version_id = selected.source_version_id
                              and (
                                version.expires_at is null
                                or version.expires_at > clock_timestamp()
                              )
                              and app.can_read_source(
                                app.current_actor_id(), selected.company_id, selected.source_id
                              )
                            """,
                            (context.company_id, snapshot.request_id, source_version_id),
                        ).fetchone()
                        if permitted is None:
                            raise PlanningStateConflictError(
                                "constraint evidence is outside the request source manifest"
                            )
                        connection.execute(
                            """
                            insert into app.constraint_source_evidence (
                              company_id, constraint_id, source_version_id
                            ) values (%s, %s, %s)
                            on conflict do nothing
                            """,
                            (context.company_id, stored_constraint_id, source_version_id),
                        )

                snapshot_json = snapshot.model_dump(mode="json")
                connection.execute(
                    """
                    insert into app.planning_snapshots (
                      id, company_id, request_id, candidate_contract_id, schema_version,
                      base_company_revision, horizon_start, horizon_end, slot_minutes,
                      source_manifest_digest, permission_revision, profile_revision,
                      estimate_revision, compiler_version, policy, normalized_snapshot,
                      snapshot_digest, frozen_at
                    ) values (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) on conflict (company_id, id) do nothing
                    """,
                    (
                        snapshot.snapshot_id,
                        context.company_id,
                        snapshot.request_id,
                        snapshot.candidate_contract_id,
                        snapshot.schema_version,
                        snapshot.base_company_revision,
                        snapshot.horizon_start,
                        snapshot.horizon_end,
                        snapshot.slot_minutes,
                        bytes.fromhex(snapshot.source_manifest_digest),
                        snapshot.permission_revision,
                        snapshot.profile_revision,
                        snapshot.estimate_revision,
                        snapshot.compiler_version,
                        Jsonb(snapshot.policy.model_dump(mode="json")),
                        Jsonb(snapshot_json),
                        bytes.fromhex(snapshot.snapshot_digest),
                        snapshot.frozen_at,
                    ),
                )
                stored_snapshot = connection.execute(
                    """
                    select snapshot_digest from app.planning_snapshots
                    where company_id = %s and id = %s
                    """,
                    (context.company_id, snapshot.snapshot_id),
                ).fetchone()
                if stored_snapshot is None or bytes(
                    stored_snapshot["snapshot_digest"]
                ) != bytes.fromhex(snapshot.snapshot_digest):
                    raise PlanningStateConflictError(
                        "snapshot ID already identifies different canonical contents"
                    )
                for ordinal, constraint_id in enumerate(constraint_ids):
                    connection.execute(
                        """
                        insert into app.planning_snapshot_constraints (
                          company_id, snapshot_id, constraint_id, ordinal
                        ) values (%s, %s, %s, %s)
                        on conflict do nothing
                        """,
                        (context.company_id, snapshot.snapshot_id, constraint_id, ordinal),
                    )
                connection.execute(
                    """
                    insert into app.trace_steps (
                      id, company_id, request_id, interpretation_run_id, step_type,
                      input_digest, output_digest, tool_version, status,
                      viewer_safe_projection
                    ) values (
                      %s, %s, %s, %s, 'snapshot_frozen', %s, %s, %s, 'complete', %s
                    ) on conflict (id) do nothing
                    """,
                    (
                        uuid5(snapshot.snapshot_id, "trace:snapshot_frozen"),
                        context.company_id,
                        snapshot.request_id,
                        current["interpretation_run_id"],
                        bytes.fromhex(snapshot.source_manifest_digest),
                        bytes.fromhex(snapshot.snapshot_digest),
                        snapshot.compiler_version,
                        Jsonb(
                            {
                                "snapshot_id": str(snapshot.snapshot_id),
                                "constraint_count": len(snapshot.constraints),
                            }
                        ),
                    ),
                )
        except PlanningStateConflictError:
            raise
        except psycopg.Error as error:
            raise PlanningPersistenceError("planning snapshot could not be stored") from error

    def save_decision(
        self,
        *,
        context: CompanyContext,
        snapshot: PlanningSnapshot,
        decision: PlanningDecision,
    ) -> UUID | None:
        if (
            context.company_id != snapshot.company_id
            or decision.snapshot_digest != snapshot.snapshot_digest
        ):
            raise PlanningStateConflictError("decision does not match the current snapshot")
        now = datetime.now(UTC)
        try:
            with company_transaction(
                self._dsn,
                role="coordination_worker",
                actor_id=context.actor.user_id,
                company_id=context.company_id,
                purpose="planning:decision",
                demo_run_id=context.demo_run_id,
                demo_actor_session_id=context.demo_actor_session_id,
                connect_timeout_seconds=self._connect_timeout_seconds,
            ) as connection:
                stored_snapshot = connection.execute(
                    """
                    select snapshot.request_id, candidate.interpretation_run_id,
                           candidate.contract_json, company.policy_revision
                    from app.planning_snapshots as snapshot
                    join app.candidate_contracts as candidate
                      on candidate.company_id = snapshot.company_id
                     and candidate.id = snapshot.candidate_contract_id
                    join app.companies as company on company.id = snapshot.company_id
                    where snapshot.company_id = %s
                      and snapshot.id = %s
                      and snapshot.snapshot_digest = %s
                    """,
                    (
                        context.company_id,
                        snapshot.snapshot_id,
                        bytes.fromhex(snapshot.snapshot_digest),
                    ),
                ).fetchone()
                if stored_snapshot is None:
                    raise PlanningStateConflictError("planning snapshot is absent or changed")

                for attempt in decision.attempts:
                    completed_at = now
                    started_at = completed_at - timedelta(milliseconds=attempt.runtime_ms)
                    connection.execute(
                        """
                        insert into app.solver_runs (
                          id, company_id, snapshot_id, scope, application_classification,
                          raw_status, termination, reason_unknown, model_digest,
                          compiler_version, solver_version, validator_version, timeout_ms,
                          resource_limit, runtime_ms, objective_vector,
                          diagnostic_constraint_keys, validation_report, started_at, completed_at
                        ) values (
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        ) on conflict (company_id, id) do nothing
                        """,
                        (
                            attempt.run_id,
                            context.company_id,
                            snapshot.snapshot_id,
                            attempt.scope,
                            attempt.classification,
                            attempt.raw_status,
                            attempt.termination,
                            attempt.reason_unknown,
                            bytes.fromhex(attempt.model.model_digest) if attempt.model else None,
                            attempt.model.compiler_version if attempt.model else None,
                            attempt.solver_version,
                            attempt.validation.validator_version if attempt.validation else None,
                            attempt.timeout_ms,
                            attempt.resource_limit,
                            attempt.runtime_ms,
                            Jsonb([value.model_dump(mode="json") for value in attempt.objectives]),
                            Jsonb(list(attempt.diagnostic_constraint_ids)),
                            Jsonb(attempt.validation.model_dump(mode="json"))
                            if attempt.validation
                            else None,
                            started_at,
                            completed_at,
                        ),
                    )
                    expected_model_digest = (
                        bytes.fromhex(attempt.model.model_digest) if attempt.model else None
                    )
                    existing_run = connection.execute(
                        """
                        select snapshot_id, raw_status, application_classification, model_digest
                        from app.solver_runs
                        where company_id = %s and id = %s
                        """,
                        (context.company_id, attempt.run_id),
                    ).fetchone()
                    if (
                        existing_run is None
                        or existing_run["snapshot_id"] != snapshot.snapshot_id
                        or existing_run["raw_status"] != attempt.raw_status
                        or existing_run["application_classification"] != attempt.classification
                        or (
                            bytes(existing_run["model_digest"])
                            if existing_run["model_digest"] is not None
                            else None
                        )
                        != expected_model_digest
                    ):
                        raise PlanningStateConflictError(
                            "solver run ID already identifies different contents"
                        )
                    connection.execute(
                        """
                        insert into app.trace_steps (
                          id, company_id, request_id, interpretation_run_id, step_type,
                          input_digest, output_digest, tool_version, status,
                          viewer_safe_projection
                        ) values (
                          %s, %s, %s, %s, 'solver_completed', %s, %s, %s, 'complete', %s
                        ) on conflict (id) do nothing
                        """,
                        (
                            uuid5(attempt.run_id, "trace:solver_completed"),
                            context.company_id,
                            snapshot.request_id,
                            stored_snapshot["interpretation_run_id"],
                            bytes.fromhex(snapshot.snapshot_digest),
                            bytes.fromhex(attempt.model.model_digest) if attempt.model else None,
                            attempt.solver_version,
                            Jsonb(
                                {
                                    "run_id": str(attempt.run_id),
                                    "scope": attempt.scope,
                                    "classification": attempt.classification,
                                    "termination": attempt.termination,
                                }
                            ),
                        ),
                    )

                if decision.selected_attempt is None:
                    return None
                selected = decision.attempts[decision.selected_attempt]
                if selected.validation is None or not selected.validation.valid:
                    raise PlanningStateConflictError(
                        "selected plan was not independently validated"
                    )
                plan_id = uuid5(snapshot.snapshot_id, selected.validation.schedule_digest)
                proposal_digest = bytes.fromhex(selected.validation.schedule_digest)
                connection.execute(
                    """
                    insert into app.plans (
                      id, company_id, request_id, snapshot_id, solver_run_id,
                      state, classification, proposal_digest
                    ) values (%s, %s, %s, %s, %s, 'proposed', %s, %s)
                    on conflict (company_id, proposal_digest) do nothing
                    """,
                    (
                        plan_id,
                        context.company_id,
                        snapshot.request_id,
                        snapshot.snapshot_id,
                        selected.run_id,
                        selected.classification,
                        proposal_digest,
                    ),
                )
                existing_plan = connection.execute(
                    """
                    select id, snapshot_id from app.plans
                    where company_id = %s and proposal_digest = %s
                    """,
                    (context.company_id, proposal_digest),
                ).fetchone()
                if existing_plan is None or existing_plan["snapshot_id"] != snapshot.snapshot_id:
                    raise PlanningStateConflictError(
                        "proposal digest already identifies a different snapshot"
                    )
                plan_id = cast(UUID, existing_plan["id"])
                for placement in selected.placements:
                    connection.execute(
                        """
                        insert into app.plan_task_placements (
                          company_id, plan_id, task_id, start_slot, end_slot, owner_resource_id
                        ) values (%s, %s, %s, %s, %s, %s)
                        on conflict do nothing
                        """,
                        (
                            context.company_id,
                            plan_id,
                            placement.task_id,
                            placement.start_slot,
                            placement.end_slot,
                            placement.owner_resource_id,
                        ),
                    )
                    existing_placement = connection.execute(
                        """
                        select start_slot, end_slot, owner_resource_id
                        from app.plan_task_placements
                        where company_id = %s and plan_id = %s and task_id = %s
                        """,
                        (context.company_id, plan_id, placement.task_id),
                    ).fetchone()
                    if existing_placement is None or (
                        existing_placement["start_slot"],
                        existing_placement["end_slot"],
                        existing_placement["owner_resource_id"],
                    ) != (
                        placement.start_slot,
                        placement.end_slot,
                        placement.owner_resource_id,
                    ):
                        raise PlanningStateConflictError(
                            "plan placement conflicts with the proposal digest"
                        )
                for block in selected.blocks:
                    connection.execute(
                        """
                        insert into app.plan_schedule_blocks (
                          company_id, plan_id, task_id, resource_id, start_slot,
                          end_slot, capacity_units, block_role
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                        on conflict do nothing
                        """,
                        (
                            context.company_id,
                            plan_id,
                            block.task_id,
                            block.resource_id,
                            block.start_slot,
                            block.end_slot,
                            block.capacity_units,
                            block.role,
                        ),
                    )
                    existing_block = connection.execute(
                        """
                        select end_slot, capacity_units
                        from app.plan_schedule_blocks
                        where company_id = %s
                          and plan_id = %s
                          and task_id = %s
                          and resource_id = %s
                          and start_slot = %s
                          and block_role = %s
                        """,
                        (
                            context.company_id,
                            plan_id,
                            block.task_id,
                            block.resource_id,
                            block.start_slot,
                            block.role,
                        ),
                    ).fetchone()
                    if existing_block is None or (
                        existing_block["end_slot"],
                        existing_block["capacity_units"],
                    ) != (block.end_slot, block.capacity_units):
                        raise PlanningStateConflictError(
                            "plan block conflicts with the proposal digest"
                        )
                connection.execute(
                    """
                    insert into app.plan_approval_requirements (
                      company_id, plan_id, approval_domain, requirement_kind,
                      authority_kind, artifact_digest, proposal_digest, snapshot_digest,
                      source_manifest_digest, base_company_revision, policy_revision,
                      policy_version, reason
                    ) values (
                      %s, %s, 'planning', 'plan_commit', 'company_manager',
                      %s, %s, %s, %s, %s, %s, %s,
                      'A manager must approve the exact independently validated proposal.'
                    ) on conflict do nothing
                    """,
                    (
                        context.company_id,
                        plan_id,
                        proposal_digest,
                        proposal_digest,
                        bytes.fromhex(snapshot.snapshot_digest),
                        bytes.fromhex(snapshot.source_manifest_digest),
                        snapshot.base_company_revision,
                        stored_snapshot["policy_revision"],
                        snapshot.policy.policy_version,
                    ),
                )
                placements_by_task = {
                    placement.task_id: placement for placement in selected.placements
                }
                for constraint in snapshot.constraints:
                    payload = constraint.payload
                    if payload.family == "deadline":
                        deadline_placement = placements_by_task.get(payload.task_id)
                        if (
                            deadline_placement is not None
                            and payload.agreed_finish_slot is not None
                            and deadline_placement.end_slot != payload.agreed_finish_slot
                        ):
                            connection.execute(
                                """
                                insert into app.plan_changes (
                                  company_id, plan_id, change_kind, summary,
                                  before_value, after_value, supporting_constraint_keys
                                ) values (
                                  %s, %s, 'deadline', %s, %s, %s, %s
                                ) on conflict do nothing
                                """,
                                (
                                    context.company_id,
                                    plan_id,
                                    "The proposed finish differs from the agreed deadline.",
                                    Jsonb({"agreed_finish_slot": payload.agreed_finish_slot}),
                                    Jsonb({"proposed_finish_slot": deadline_placement.end_slot}),
                                    Jsonb([constraint.constraint_id]),
                                ),
                            )
                            connection.execute(
                                """
                                insert into app.plan_approval_requirements (
                                  company_id, plan_id, approval_domain, requirement_kind,
                                  authority_kind, artifact_digest, proposal_digest,
                                  snapshot_digest, source_manifest_digest,
                                  base_company_revision, policy_revision, policy_version, reason
                                ) values (
                                  %s, %s, 'planning', 'deadline_change', 'company_manager',
                                  %s, %s, %s, %s, %s, %s, %s,
                                  'Confirm the proposed movement of an agreed deadline.'
                                ) on conflict do nothing
                                """,
                                (
                                    context.company_id,
                                    plan_id,
                                    proposal_digest,
                                    proposal_digest,
                                    bytes.fromhex(snapshot.snapshot_digest),
                                    bytes.fromhex(snapshot.source_manifest_digest),
                                    snapshot.base_company_revision,
                                    stored_snapshot["policy_revision"],
                                    snapshot.policy.policy_version,
                                ),
                            )
                    if payload.family == "movement" and payload.movement == "authorized":
                        movement_placement = placements_by_task.get(payload.task_id)
                        proposed_slots = tuple(
                            sorted(
                                {
                                    slot
                                    for block in selected.blocks
                                    if block.task_id == payload.task_id and block.role == "owner"
                                    for slot in range(block.start_slot, block.end_slot)
                                }
                            )
                        )
                        if movement_placement is not None and (
                            movement_placement.owner_resource_id != payload.existing_resource_id
                            or proposed_slots != payload.existing_slots
                        ):
                            connection.execute(
                                """
                                insert into app.plan_changes (
                                  company_id, plan_id, change_kind, summary,
                                  before_value, after_value, supporting_constraint_keys
                                ) values (
                                  %s, %s, 'cross_team_displacement', %s, %s, %s, %s
                                ) on conflict do nothing
                                """,
                                (
                                    context.company_id,
                                    plan_id,
                                    "Authorized existing work is displaced by this proposal.",
                                    Jsonb(
                                        {
                                            "owner_resource_id": str(payload.existing_resource_id),
                                            "slots": list(payload.existing_slots),
                                        }
                                    ),
                                    Jsonb(
                                        {
                                            "owner_resource_id": str(
                                                movement_placement.owner_resource_id
                                            ),
                                            "slots": list(proposed_slots),
                                        }
                                    ),
                                    Jsonb([constraint.constraint_id]),
                                ),
                            )
                            connection.execute(
                                """
                                insert into app.plan_approval_requirements (
                                  company_id, plan_id, approval_domain, requirement_kind,
                                  authority_kind, artifact_digest, proposal_digest,
                                  snapshot_digest, source_manifest_digest,
                                  base_company_revision, policy_revision, policy_version, reason
                                ) values (
                                  %s, %s, 'planning', 'cross_team_displacement',
                                  'company_admin', %s, %s, %s, %s, %s, %s, %s,
                                  'Affected-team mapping is absent; ' ||
                                  'company-admin authority is required.'
                                ) on conflict do nothing
                                """,
                                (
                                    context.company_id,
                                    plan_id,
                                    proposal_digest,
                                    proposal_digest,
                                    bytes.fromhex(snapshot.snapshot_digest),
                                    bytes.fromhex(snapshot.source_manifest_digest),
                                    snapshot.base_company_revision,
                                    stored_snapshot["policy_revision"],
                                    snapshot.policy.policy_version,
                                ),
                            )
                contract = CandidateTaskContract.model_validate(stored_snapshot["contract_json"])
                owner_ids = tuple(
                    sorted(
                        {
                            placement.owner_resource_id
                            for placement in selected.placements
                            if placement.owner_resource_id is not None
                        },
                        key=str,
                    )
                )
                employee_rows = connection.execute(
                    """
                    select employee_id from app.execution_resources
                    where company_id = %s and id = any(%s)
                      and resource_kind = 'human' and employee_id is not null
                    order by employee_id
                    """,
                    (context.company_id, list(owner_ids) or [UUID(int=0)]),
                ).fetchall()
                audience_ids = tuple(row["employee_id"] for row in employee_rows)
                if len(audience_ids) != len(owner_ids):
                    raise PlanningStateConflictError("plan owner cannot receive an employee brief")
                brief_payload = {
                    "schema_version": "employee-brief.v1",
                    "summary": "Complete the approved tasks within the committed schedule.",
                    "tasks": [
                        {
                            "task_key": task.task_key,
                            "title": task.title,
                            "purpose": task.purpose,
                            "deliverable": task.deliverable,
                            "acceptance_criteria": list(task.acceptance_criteria),
                        }
                        for task in contract.tasks
                    ],
                }
                audience_scope = {
                    "employee_ids": [str(employee_id) for employee_id in audience_ids],
                    "team_ids": [],
                }
                brief_digest = bytes.fromhex(
                    canonical_digest(
                        {
                            "brief_payload": brief_payload,
                            "audience_scope": audience_scope,
                        }
                    )
                )
                brief_id = uuid5(plan_id, "employee-brief:v1")
                try:
                    # A plain insert avoids applying self-referential brief SELECT
                    # policies to a not-yet-visible ON CONFLICT target row.
                    with connection.transaction():
                        connection.execute(
                            """
                            insert into app.employee_brief_versions (
                              id, company_id, plan_id, version, brief_payload,
                              audience_scope, brief_digest
                            ) values (%s, %s, %s, 1, %s, %s, %s)
                            """,
                            (
                                brief_id,
                                context.company_id,
                                plan_id,
                                Jsonb(brief_payload),
                                Jsonb(audience_scope),
                                brief_digest,
                            ),
                        )
                except psycopg.errors.UniqueViolation as error:
                    if error.diag.constraint_name != EMPLOYEE_BRIEF_VERSION_CONSTRAINT:
                        raise
                stored_brief = connection.execute(
                    """
                    select brief_digest from app.employee_brief_versions
                    where company_id = %s and plan_id = %s and version = 1
                    """,
                    (context.company_id, plan_id),
                ).fetchone()
                if stored_brief is None or bytes(stored_brief["brief_digest"]) != brief_digest:
                    raise PlanningStateConflictError(
                        "employee brief version conflicts with the proposal"
                    )
                connection.execute(
                    """
                    insert into app.trace_steps (
                      id, company_id, request_id, interpretation_run_id, step_type,
                      input_digest, output_digest, tool_version, status,
                      viewer_safe_projection
                    ) values (
                      %s, %s, %s, %s, 'schedule_validated', %s, %s, %s, 'complete', %s
                    ) on conflict (id) do nothing
                    """,
                    (
                        uuid5(plan_id, "trace:schedule_validated"),
                        context.company_id,
                        snapshot.request_id,
                        stored_snapshot["interpretation_run_id"],
                        bytes.fromhex(snapshot.snapshot_digest),
                        proposal_digest,
                        selected.validation.validator_version,
                        Jsonb(
                            {
                                "plan_id": str(plan_id),
                                "classification": selected.classification,
                                "block_count": len(selected.blocks),
                            }
                        ),
                    ),
                )
                return plan_id
        except PlanningStateConflictError:
            raise
        except (IndexError, psycopg.Error) as error:
            raise PlanningPersistenceError("planning decision could not be stored") from error
