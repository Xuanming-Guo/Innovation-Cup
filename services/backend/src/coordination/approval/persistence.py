from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from typing import Any, NoReturn, Protocol, cast
from uuid import UUID

import psycopg

from coordination.approval.contracts import (
    ApprovalCommand,
    ApprovalDecisionResult,
    ApprovalRequirementStatus,
    ApprovalRequirementView,
    CommitCommand,
    CommitResult,
    ConstraintEvidence,
    PlanBinding,
    PlanChangeView,
    PlanEvidence,
    PlanReview,
    PlanReviewStatus,
    PlanTaskView,
    SolverDiagnostic,
)
from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.planning.fixed_contracts import (
    FixedCheckReport,
    FixedValidationReport,
    PlanProposalV2,
)


class ApprovalStoreError(RuntimeError):
    """The approval store could not complete a safe operation."""


class PlanNotFoundError(LookupError):
    """No readable plan exists in the active company context."""


class ApprovalStaleError(ValueError):
    """The proposal, source, base revision or policy binding changed."""


class ApprovalAuthorityError(PermissionError):
    """The current actor does not satisfy the requested authority."""


class ApprovalIncompleteError(PermissionError):
    """One or more exact planning approvals are absent or expired."""


class ApprovalIdempotencyConflictError(ValueError):
    """An idempotency key was reused for a different command."""


class ScheduleConflictError(ValueError):
    """The approved schedule conflicts with current committed state."""


class ApprovalStore(Protocol):
    def get_review(self, *, context: CompanyContext, plan_id: UUID) -> PlanReview: ...

    def get_evidence(self, *, context: CompanyContext, plan_id: UUID) -> PlanEvidence: ...

    def decide(
        self, *, context: CompanyContext, plan_id: UUID, command: ApprovalCommand
    ) -> ApprovalDecisionResult: ...

    def commit(
        self, *, context: CompanyContext, plan_id: UUID, command: CommitCommand
    ) -> CommitResult: ...


def _hex(value: Any) -> str:
    return bytes(value).hex()


def _review_status(
    *, committed: bool, binding_current: bool, planning_statuses: list[str]
) -> PlanReviewStatus:
    if committed:
        return "committed"
    if not binding_current:
        return "stale"
    if "rejected" in planning_statuses:
        return "rejected"
    if planning_statuses and all(status == "approved" for status in planning_statuses):
        return "approved"
    return "proposed"


def read_review_status(
    connection: Any, *, context: CompanyContext, plan_id: UUID
) -> PlanReviewStatus:
    """Read approval eligibility without rebuilding tasks or opening a second transaction."""
    plan = connection.execute(
        """
        select snapshot.base_company_revision,
          app.scope_planning_revision(plan.company_id,false) as planning_revision,
          app.plan_sources_are_current(plan.company_id,plan.id) as sources_current,
          exists(select 1 from app.plan_commitments commitment
            where commitment.company_id=plan.company_id and commitment.plan_id=plan.id)
            as committed
        from app.plans plan
        join app.planning_snapshots snapshot
          on snapshot.company_id=plan.company_id and snapshot.id=plan.snapshot_id
        where plan.company_id=%s and plan.id=%s
          and plan.demo_run_id is not distinct from %s
        """,
        (context.company_id, plan_id, context.demo_run_id),
    ).fetchone()
    if plan is None:
        raise PlanNotFoundError("plan was not found")
    rows = connection.execute(
        """
        select decision.decision,decision.expires_at
        from app.plan_approval_requirements requirement
        left join lateral (
          select latest.decision,latest.expires_at
          from app.plan_approval_decisions latest
          where latest.company_id=requirement.company_id
            and latest.requirement_id=requirement.id
          order by latest.decided_at desc,latest.id desc limit 1
        ) decision on true
        where requirement.company_id=%s and requirement.plan_id=%s
          and requirement.approval_domain='planning'
        """,
        (context.company_id, plan_id),
    ).fetchall()
    now = datetime.now(UTC)
    statuses = [
        "expired"
        if row["decision"] == "approved"
        and row["expires_at"] is not None
        and row["expires_at"] <= now
        else row["decision"] or "pending"
        for row in rows
    ]
    return _review_status(
        committed=bool(plan["committed"]),
        binding_current=plan["planning_revision"] == plan["base_company_revision"]
        and bool(plan["sources_current"]),
        planning_statuses=statuses,
    )


def _fixed_review_tasks(
    connection: Any, *, context: CompanyContext, plan: dict[str, Any]
) -> tuple[PlanTaskView, ...]:
    """Project the exact fixed proposal without rebuilding its constraint graph."""
    stored = connection.execute(
        """
        select candidate_payload, candidate_digest, author_kind
        from app.ai_plan_proposals
        where company_id = %s and id = %s and snapshot_id = %s
          and demo_run_id is not distinct from %s
        """,
        (context.company_id, plan["ai_proposal_id"], plan["snapshot_id"], context.demo_run_id),
    ).fetchone()
    if stored is None:
        raise ApprovalStoreError("the exact fixed proposal is unavailable")

    try:
        proposal = PlanProposalV2.model_validate(stored["candidate_payload"]["proposal"])
        if (
            proposal.proposal_id != plan["ai_proposal_id"]
            or proposal.company_id != context.company_id
            or proposal.demo_run_id != context.demo_run_id
            or proposal.demo_run_id != plan["demo_run_id"]
            or proposal.request_id != plan["request_id"]
            or proposal.snapshot_id != plan["snapshot_id"]
            or proposal.snapshot_digest != _hex(plan["snapshot_digest"])
            or proposal.source_manifest_digest != _hex(plan["source_manifest_digest"])
            or proposal.candidate_digest != _hex(stored["candidate_digest"])
            or proposal.candidate_digest != _hex(plan["proposal_digest"])
            or proposal.author_kind != stored["author_kind"]
            or proposal.author_kind != plan["author_kind"]
        ):
            raise ApprovalStoreError("the fixed proposal does not match the plan binding")

        placements = connection.execute(
            """
            select task_id, start_slot, end_slot, owner_resource_id
            from app.plan_task_placements
            where company_id = %s and plan_id = %s
              and demo_run_id is not distinct from %s
            """,
            (context.company_id, plan["id"], context.demo_run_id),
        ).fetchall()
        definitions = {task.task_id: task for task in proposal.draft.tasks}
        if (
            len(definitions) != len(proposal.draft.tasks)
            or len(placements) != len(definitions)
            or {row["task_id"] for row in placements} != set(definitions)
        ):
            raise ApprovalStoreError("the fixed proposal task set does not match its placements")

        horizon_start = cast(datetime, plan["horizon_start"]).astimezone(UTC)
        slot_minutes = cast(int, plan["slot_minutes"])
        tasks = []
        for row in placements:
            task = definitions[row["task_id"]]
            start_at = horizon_start + timedelta(minutes=row["start_slot"] * slot_minutes)
            finish_at = horizon_start + timedelta(minutes=row["end_slot"] * slot_minutes)
            if (
                task.owner_resource_id != row["owner_resource_id"]
                or task.start.astimezone(UTC) != start_at
                or task.end.astimezone(UTC) != finish_at
            ):
                raise ApprovalStoreError(
                    "the fixed proposal schedule does not match its placements"
                )
            tasks.append(
                PlanTaskView(
                    task_id=task.task_id,
                    task_key=task.task_key,
                    title=task.title,
                    scheduling_kind=task.scheduling_kind,
                    start_at=start_at,
                    finish_at=finish_at,
                    owner_resource_id=row["owner_resource_id"],
                )
            )
        return tuple(sorted(tasks, key=lambda task: (task.start_at, task.task_key)))
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ApprovalStoreError("the stored fixed proposal could not be read safely") from error


class PostgresApprovalStore:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _transaction(self, context: CompanyContext, purpose: str) -> AbstractContextManager[Any]:
        return company_transaction(
            self._dsn,
            role="coordination_api",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            purpose=purpose,
            demo_run_id=context.demo_run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def get_review(self, *, context: CompanyContext, plan_id: UUID) -> PlanReview:
        try:
            with self._transaction(context, "approval:review") as connection:
                plan = connection.execute(
                    """
                    select plan.id, plan.request_id, plan.classification, plan.proposal_digest,
                           plan.author_kind, plan.ai_proposal_id, plan.snapshot_id,
                           plan.demo_run_id,
                           request.original_prompt, snapshot.snapshot_digest,
                           snapshot.source_manifest_digest, snapshot.base_company_revision,
                           snapshot.horizon_start, snapshot.slot_minutes,
                           snapshot.policy ->> 'policy_version' as policy_version,
                           app.scope_planning_revision(company.id,false) as planning_revision,
                             company.policy_revision,
                           commitment.id as commitment_id,
                           app.plan_sources_are_current(plan.company_id, plan.id) as sources_current
                    from app.plans as plan
                    join app.planning_requests as request
                      on request.company_id = plan.company_id and request.id = plan.request_id
                    join app.planning_snapshots as snapshot
                      on snapshot.company_id = plan.company_id and snapshot.id = plan.snapshot_id
                    join app.companies as company on company.id = plan.company_id
                    left join app.plan_commitments as commitment
                      on commitment.company_id = plan.company_id and commitment.plan_id = plan.id
                    where plan.company_id = %s and plan.id = %s
                      and plan.demo_run_id is not distinct from %s
                    """,
                    (context.company_id, plan_id, context.demo_run_id),
                ).fetchone()
                if plan is None:
                    raise PlanNotFoundError("plan was not found")

                if plan["author_kind"] != "legacy_solver":
                    tasks = _fixed_review_tasks(connection, context=context, plan=plan)
                else:
                    task_rows = connection.execute(
                        """
                        select placement.task_id, placement.start_slot, placement.end_slot,
                               placement.owner_resource_id, definition.payload
                        from app.plan_task_placements as placement
                        join app.plans as plan
                          on plan.company_id = placement.company_id and plan.id = placement.plan_id
                        join app.validated_constraints as definition
                          on definition.company_id = placement.company_id
                         and definition.request_id = plan.request_id
                         and definition.payload ->> 'family' = 'task_definition'
                         and definition.payload ->> 'task_id' = placement.task_id::text
                        join app.planning_snapshot_constraints as snapshot_member
                          on snapshot_member.company_id = plan.company_id
                         and snapshot_member.snapshot_id = plan.snapshot_id
                         and snapshot_member.constraint_id = definition.id
                        where placement.company_id = %s and placement.plan_id = %s
                        order by placement.start_slot, definition.payload ->> 'task_key'
                        """,
                        (context.company_id, plan_id),
                    ).fetchall()
                    slot_minutes = cast(int, plan["slot_minutes"])
                    horizon_start = plan["horizon_start"]
                    tasks = tuple(
                        PlanTaskView(
                            task_id=row["task_id"],
                            task_key=row["payload"]["task_key"],
                            title=row["payload"]["title"],
                            scheduling_kind=row["payload"]["scheduling_kind"],
                            start_at=horizon_start
                            + timedelta(minutes=row["start_slot"] * slot_minutes),
                            finish_at=horizon_start
                            + timedelta(minutes=row["end_slot"] * slot_minutes),
                            owner_resource_id=row["owner_resource_id"],
                        )
                        for row in task_rows
                    )

                change_rows = connection.execute(
                    """
                    select id, change_kind, summary, affected_team_id, before_value,
                           after_value, supporting_constraint_keys
                    from app.plan_changes where company_id = %s and plan_id = %s
                    order by created_at, id
                    """,
                    (context.company_id, plan_id),
                ).fetchall()
                changes = tuple(
                    PlanChangeView(
                        change_id=row["id"],
                        kind=row["change_kind"],
                        summary=row["summary"],
                        affected_team_id=row["affected_team_id"],
                        before_value=row["before_value"],
                        after_value=row["after_value"],
                        supporting_constraint_keys=tuple(row["supporting_constraint_keys"]),
                    )
                    for row in change_rows
                )

                requirement_rows = connection.execute(
                    """
                    select requirement.id, requirement.approval_domain,
                           requirement.requirement_kind, requirement.authority_kind,
                           requirement.authority_team_id, requirement.artifact_digest,
                           requirement.reason,
                           decision.decision, decision.actor_membership_id,
                           decision.decided_at, decision.expires_at
                    from app.plan_approval_requirements as requirement
                    left join lateral (
                      select latest.decision, latest.actor_membership_id,
                             latest.decided_at, latest.expires_at
                      from app.plan_approval_decisions as latest
                      where latest.company_id = requirement.company_id
                        and latest.requirement_id = requirement.id
                      order by latest.decided_at desc, latest.id desc limit 1
                    ) as decision on true
                    where requirement.company_id = %s and requirement.plan_id = %s
                    order by requirement.approval_domain, requirement.requirement_kind,
                             requirement.authority_team_id nulls first
                    """,
                    (context.company_id, plan_id),
                ).fetchall()
                requirements: list[ApprovalRequirementView] = []
                for row in requirement_rows:
                    requirement_status = cast(
                        ApprovalRequirementStatus, row["decision"] or "pending"
                    )
                    if (
                        requirement_status == "approved"
                        and row["expires_at"] is not None
                        and row["expires_at"] <= datetime.now(UTC)
                    ):
                        requirement_status = "expired"
                    requirements.append(
                        ApprovalRequirementView(
                            requirement_id=row["id"],
                            domain=row["approval_domain"],
                            kind=row["requirement_kind"],
                            authority_kind=row["authority_kind"],
                            authority_team_id=row["authority_team_id"],
                            artifact_digest=_hex(row["artifact_digest"]),
                            reason=row["reason"],
                            status=requirement_status,
                            decided_by_membership_id=row["actor_membership_id"],
                            decided_at=row["decided_at"],
                            expires_at=row["expires_at"],
                        )
                    )

                planning_requirements = [
                    requirement for requirement in requirements if requirement.domain == "planning"
                ]
                binding_current = plan["planning_revision"] == plan[
                    "base_company_revision"
                ] and bool(plan["sources_current"])
                review_status = _review_status(
                    committed=plan["commitment_id"] is not None,
                    binding_current=binding_current,
                    planning_statuses=[item.status for item in planning_requirements],
                )

                return PlanReview(
                    plan_id=plan["id"],
                    request_id=plan["request_id"],
                    request_summary=plan["original_prompt"],
                    classification=plan["classification"],
                    status=review_status,
                    binding=PlanBinding(
                        proposal_digest=_hex(plan["proposal_digest"]),
                        snapshot_digest=_hex(plan["snapshot_digest"]),
                        source_manifest_digest=_hex(plan["source_manifest_digest"]),
                        base_company_revision=plan["base_company_revision"],
                        policy_revision=plan["policy_revision"],
                        policy_version=plan["policy_version"],
                    ),
                    tasks=tasks,
                    changes=changes,
                    requirements=tuple(requirements),
                    can_commit=review_status == "approved",
                    author_kind=plan["author_kind"],
                )
        except PlanNotFoundError:
            raise
        except psycopg.Error as error:
            raise ApprovalStoreError("plan review could not be loaded") from error

    def get_evidence(self, *, context: CompanyContext, plan_id: UUID) -> PlanEvidence:
        try:
            with self._transaction(context, "approval:evidence") as connection:
                solver = connection.execute(
                    """
                    select plan.author_kind, run.application_classification, run.raw_status,
                      run.termination,
                           run.solver_version, run.compiler_version, run.validator_version,
                           run.runtime_ms, run.objective_vector,
                           run.diagnostic_constraint_keys,
                           verification.diagnostics as fixed_report,
                           validation.validator_version as fixed_validator_version,
                           validation.passed as fixed_validation_passed,
                           validation.candidate_digest as fixed_validation_digest,
                           validation.issues as fixed_validation_issues,
                           verification.snapshot_digest as fixed_snapshot_digest
                    from app.plans as plan
                    left join app.solver_runs as run
                      on run.company_id = plan.company_id and run.id = plan.solver_run_id
                    left join app.plan_verification_runs verification
                      on verification.company_id=plan.company_id and
                        verification.id=plan.verification_run_id
                    left join app.plan_validation_runs validation
                      on validation.company_id=plan.company_id and
                        validation.id=plan.validation_run_id
                    where plan.company_id = %s and plan.id = %s
                    """,
                    (context.company_id, plan_id),
                ).fetchone()
                if solver is None:
                    raise PlanNotFoundError("plan was not found")
                rows = connection.execute(
                    """
                    select constraint.constraint_key, constraint.strength,
                           constraint.confidentiality, constraint.payload ->> 'family' as family,
                           constraint.source_version_ids, constraint.authority_refs
                    from app.plans as plan
                    join app.planning_snapshot_constraints as member
                      on member.company_id = plan.company_id
                     and member.snapshot_id = plan.snapshot_id
                    join app.validated_constraints as constraint
                      on constraint.company_id = member.company_id
                     and constraint.id = member.constraint_id
                    where plan.company_id = %s and plan.id = %s
                    order by member.ordinal
                    """,
                    (context.company_id, plan_id),
                ).fetchall()
                constraints = tuple(
                    ConstraintEvidence(
                        constraint_key=row["constraint_key"],
                        family=row["family"],
                        strength=row["strength"],
                        confidentiality=row["confidentiality"],
                        source_version_ids=tuple(
                            UUID(value) for value in row["source_version_ids"]
                        ),
                        authority_refs=tuple(row["authority_refs"]),
                    )
                    for row in rows
                )
                assumptions = tuple(
                    sorted(
                        {
                            authority
                            for constraint in constraints
                            for authority in constraint.authority_refs
                        }
                    )
                )
                return PlanEvidence(
                    plan_id=plan_id,
                    constraints=constraints,
                    assumptions=assumptions,
                    author_kind=solver["author_kind"],
                    fixed_verification=FixedCheckReport.model_validate(
                        solver["fixed_report"]["report"]
                    )
                    if solver["fixed_report"] is not None
                    else None,
                    independent_validation=FixedValidationReport(
                        validator_version=solver["fixed_validator_version"],
                        candidate_digest=_hex(solver["fixed_validation_digest"]),
                        snapshot_digest=_hex(solver["fixed_snapshot_digest"]),
                        passed=solver["fixed_validation_passed"],
                        issues=solver["fixed_validation_issues"],
                    )
                    if solver["fixed_validator_version"] is not None
                    else None,
                    solver=SolverDiagnostic(
                        classification=solver["application_classification"],
                        raw_status=solver["raw_status"],
                        termination=solver["termination"],
                        solver_version=solver["solver_version"],
                        compiler_version=solver["compiler_version"],
                        validator_version=solver["validator_version"],
                        runtime_ms=solver["runtime_ms"],
                        objective_vector=tuple(solver["objective_vector"]),
                        diagnostic_constraint_keys=tuple(solver["diagnostic_constraint_keys"]),
                    )
                    if solver["application_classification"] is not None
                    else None,
                )
        except PlanNotFoundError:
            raise
        except psycopg.Error as error:
            raise ApprovalStoreError("plan evidence could not be loaded") from error

    def decide(
        self, *, context: CompanyContext, plan_id: UUID, command: ApprovalCommand
    ) -> ApprovalDecisionResult:
        try:
            with self._transaction(context, "approval:decide") as connection:
                row = connection.execute(
                    """
                    select * from app.record_plan_approval_decision(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        plan_id,
                        command.requirement_id,
                        command.decision,
                        command.explanation,
                        bytes.fromhex(command.artifact_digest),
                        bytes.fromhex(command.binding.proposal_digest),
                        bytes.fromhex(command.binding.snapshot_digest),
                        bytes.fromhex(command.binding.source_manifest_digest),
                        command.binding.base_company_revision,
                        command.binding.policy_revision,
                        command.binding.policy_version,
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError("approval decision returned no result")
                return ApprovalDecisionResult(
                    decision_id=row["decision_id"],
                    decision=row["recorded_decision"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    def commit(
        self, *, context: CompanyContext, plan_id: UUID, command: CommitCommand
    ) -> CommitResult:
        try:
            with self._transaction(context, "approval:commit") as connection:
                row = connection.execute(
                    """
                    select * from app.commit_approved_plan(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        plan_id,
                        bytes.fromhex(command.binding.proposal_digest),
                        bytes.fromhex(command.binding.snapshot_digest),
                        bytes.fromhex(command.binding.source_manifest_digest),
                        command.binding.base_company_revision,
                        command.binding.policy_revision,
                        command.binding.policy_version,
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise ApprovalStoreError("plan commitment returned no result")
                return CommitResult(
                    commitment_id=row["commitment_id"],
                    status=row["commit_status"],
                    company_revision=row["committed_revision"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    @staticmethod
    def _translate(error: psycopg.Error) -> NoReturn:
        message = str(error)
        if error.sqlstate == "P0002" or "not_found" in message:
            raise PlanNotFoundError("plan approval resource was not found") from error
        if error.sqlstate == "40001" or "stale" in message:
            raise ApprovalStaleError("the exact plan binding is stale") from error
        if "approval_incomplete" in message:
            raise ApprovalIncompleteError("required planning approvals are incomplete") from error
        if error.sqlstate == "42501":
            raise ApprovalAuthorityError("required approval authority is absent") from error
        if error.sqlstate == "23505" or "idempotency" in message:
            raise ApprovalIdempotencyConflictError("idempotency key was reused") from error
        if error.sqlstate == "23P01" or "schedule" in message:
            raise ScheduleConflictError("committed schedule changed; replan is required") from error
        raise ApprovalStoreError("approval operation could not be stored") from error
