"""Finite admission of the operator-versioned Northstar authority pack.

This supplements the v1 interpretation contract with facts that contract cannot
express. It never imports the authored P1/D0 candidate or chooses a live schedule.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from coordination.interpretation.admission import AdmissionIssue, AdmissionResult
from coordination.interpretation.contracts import CandidateTaskContract, EvidenceBasis
from coordination.planning.contracts import (
    DailyBudget,
    PlanningPolicy,
    PlanningSnapshot,
    ReservationPayload,
    ResourceCapacityPayload,
    TaskDefinitionPayload,
    WorkingWindowPayload,
)
from coordination.planning.materializer import MaterializationError, PlanningResourceProfile
from coordination.planning.northstar import (
    GATES,
    NORTHSTAR_SCENARIO_VERSION,
    NORTHSTAR_TIMEZONE,
    REVIEWS,
    TASKS,
    build_northstar_snapshot,
    person_id,
    task_id,
)


class AuthorityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TaskAuthority(AuthorityModel):
    task_key: str
    active_minutes: int = Field(gt=0, le=420)
    eligible_person_keys: tuple[str, ...] = Field(min_length=1, max_length=10)
    scheduling_kind: Literal["flexible_active", "review"]
    review_policy: Literal["exact_review", "self_certifiable_internal_draft", "not_required"]
    review_task_keys: tuple[str, ...]
    active_participant_keys: tuple[str, ...]


class GateAuthority(AuthorityModel):
    predecessor_task_key: str
    successor_task_key: str
    required_state: Literal["submitted", "accepted", "approved", "self_certified"]
    minimum_lag_minutes: Literal[0] = 0
    artifact_version_policy: Literal["exact_submitted_version"] = "exact_submitted_version"


class NorthstarAuthorityManifest(AuthorityModel):
    schema_version: Literal["northstar-planning-authority.v1"]
    scenario_version: Literal["northstar-launch.2026-09.v1"]
    timezone: Literal["America/Los_Angeles"]
    tasks: tuple[TaskAuthority, ...] = Field(min_length=17, max_length=17)
    gates: tuple[GateAuthority, ...] = Field(min_length=22, max_length=22)
    release_task_key: Literal["l1"]
    release_start: datetime
    release_finish: datetime
    completion_task_key: Literal["r2"]
    completion_deadline: datetime


def canonical_authority_manifest() -> NorthstarAuthorityManifest:
    """Only work/authority/real boundaries, no authored candidate owner/time choices."""
    zone = ZoneInfo(NORTHSTAR_TIMEZONE)
    tasks = []
    for key, _day, start, end, owner, _title, _deliverable in TASKS:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        tasks.append(
            TaskAuthority(
                task_key=key,
                active_minutes=(eh - sh) * 60 + em - sm,
                eligible_person_keys=(owner,),
                scheduling_kind="review" if key in {*REVIEWS.values(), "r1"} else "flexible_active",
                review_policy="exact_review"
                if key in REVIEWS
                else "self_certifiable_internal_draft"
                if key in ("m1", "s1")
                else "not_required",
                review_task_keys=(REVIEWS[key],) if key in REVIEWS else (),
                active_participant_keys=("nora",) if key == "l1" else (),
            )
        )
    return NorthstarAuthorityManifest(
        schema_version="northstar-planning-authority.v1",
        scenario_version=NORTHSTAR_SCENARIO_VERSION,
        timezone=NORTHSTAR_TIMEZONE,
        tasks=tuple(tasks),
        gates=tuple(
            GateAuthority(predecessor_task_key=pre, successor_task_key=post, required_state=state)
            for pre, post, state in GATES
        ),
        release_task_key="l1",
        release_start=datetime(2026, 10, 2, 10, tzinfo=zone),
        release_finish=datetime(2026, 10, 2, 10, 30, tzinfo=zone),
        completion_task_key="r2",
        completion_deadline=datetime(2026, 10, 2, 11, 15, tzinfo=zone),
    )


def admit_live_northstar_contract(
    *,
    company_id: UUID,
    request_id: UUID,
    contract: CandidateTaskContract,
    source_version_ids: dict[str, UUID],
    authority: NorthstarAuthorityManifest,
) -> AdmissionResult:
    """Validate model representation, never replace it with authored work.

    The caller must authenticate the pinned operator manifest and current selected
    source versions before invoking this adapter. The same check runs again at
    materialization so pre-admission cannot weaken the commit boundary.
    """
    if authority != canonical_authority_manifest():
        raise MaterializationError("the pinned authority manifest is not a supported exact version")
    if set(source_version_ids) != {f"LAUNCH-{index:02}" for index in range(1, 8)}:
        raise MaterializationError("the complete pinned source authority is required")
    issues: list[AdmissionIssue] = []

    def reject(code: str, path: str, message: str) -> None:
        issues.append(AdmissionIssue(code=code, path=path, message=message, disposition="reject"))

    if contract.company_id != company_id or contract.request_id != request_id:
        reject(
            "finite_identity_mismatch", "request_id", "contract identity differs from its request"
        )
    if contract.assumptions or contract.clarifications or contract.unsupported:
        issues.append(
            AdmissionIssue(
                code="finite_authority_unresolved",
                path="assumptions",
                message="The live contract still contains assumptions or unresolved decisions.",
                disposition="clarify",
            )
        )
    expected_tasks = {item.task_key: item for item in authority.tasks}
    actual_tasks = {item.task_key: item for item in contract.tasks}
    if len(actual_tasks) != len(contract.tasks) or actual_tasks.keys() != expected_tasks.keys():
        reject(
            "finite_task_catalogue_mismatch",
            "tasks",
            "Return every exact task key from the authoritative catalogue; add no extra work.",
        )
    expected_edges = {
        (gate.predecessor_task_key, gate.successor_task_key) for gate in authority.gates
    }
    actual_edges = {
        (edge.predecessor_task_key, edge.successor_task_key) for edge in contract.dependencies
    }
    if actual_edges != expected_edges or len(actual_edges) != len(contract.dependencies):
        reject(
            "finite_gate_catalogue_mismatch",
            "dependencies",
            "Return every exact gate endpoint pair from the pinned authority, without duplicates.",
        )
    for task_index, task in enumerate(contract.tasks):
        rule = expected_tasks.get(task.task_key)
        if rule is None:
            continue
        path = f"tasks[{task_index}]"
        if (
            task.timing_type != "flexible_active"
            or task.estimate.active_minutes != rule.active_minutes
        ):
            reject(
                "finite_effort_or_kind_mismatch",
                path,
                f"Task {rule.task_key} uses flexible_active in this contract with exactly "
                f"{rule.active_minutes} active minutes; admission restores its review policy.",
            )
        if task.deadline is not None and not (
            task.task_key == "r2"
            and task.deadline.requested_at == authority.completion_deadline
            and task.deadline.flexibility == "fixed"
        ):
            reject(
                "finite_deadline_mismatch",
                f"{path}.deadline",
                "Only the authoritative R2 completion deadline is a task finish deadline; "
                "release start is represented separately by trusted authority.",
            )
        if not any(
            isinstance(basis, EvidenceBasis)
            and basis.source_version_id == source_version_ids["LAUNCH-02"]
            and basis.locator == "LAUNCH-02"
            for basis in task.bases
        ):
            reject(
                "finite_task_source_mismatch",
                f"{path}.bases",
                f"Task {rule.task_key} must cite the exact LAUNCH-02 source version and locator.",
            )
        for requirement_index, requirement in enumerate(task.requirements):
            if requirement.strength != "hard":
                continue
            if requirement.minimum_level is not None:
                reject(
                    "finite_qualification_level_mismatch",
                    f"{path}.requirements[{requirement_index}].minimum_level",
                    "No numeric qualification level is authorized by the pinned source pack.",
                )
            supported = requirement.kind in (
                "skill",
                "qualification",
            ) and requirement.requirement_key in {
                "northstar." + key for key in rule.eligible_person_keys
            }
            supported |= (
                requirement.kind in ("permission", "input")
                and requirement.requirement_key == "northstar.launch"
            )
            supported |= (
                requirement.kind == "review"
                and requirement.requirement_key in rule.review_task_keys
            )
            if not supported:
                eligible = ", ".join("northstar." + key for key in rule.eligible_person_keys)
                reject(
                    "finite_requirement_mismatch",
                    f"{path}.requirements[{requirement_index}]",
                    f"Task {rule.task_key} authorizes only {eligible} as hard skill/qualification "
                    "eligibility, northstar.launch as permission/input, and its exact declared "
                    "review keys. Correct the requirement from this task's authority; a person's "
                    "presence in the employee list does not grant task eligibility.",
                )
    for edge_index, edge in enumerate(contract.dependencies):
        path = f"dependencies[{edge_index}]"
        if edge.minimum_lag_minutes or edge.dependency_type == "information":
            reject(
                "finite_gate_timing_mismatch",
                path,
                "Authoritative execution gates require zero lag and a temporal dependency.",
            )
        if not any(
            isinstance(basis, EvidenceBasis)
            and basis.source_version_id == source_version_ids["LAUNCH-07"]
            and basis.locator == "LAUNCH-07"
            for basis in edge.bases
        ):
            reject(
                "finite_gate_source_mismatch",
                f"{path}.bases",
                "Each gate must cite the supplied LAUNCH-07 source version and locator.",
            )
    return AdmissionResult(
        status="rejected"
        if any(issue.disposition == "reject" for issue in issues)
        else "clarification_required"
        if issues
        else "admitted",
        issues=tuple(issues),
    )


def build_live_northstar_snapshot(
    *,
    company_id: UUID,
    run_id: UUID,
    request_id: UUID,
    candidate_contract_id: UUID,
    contract: CandidateTaskContract,
    source_version_ids: dict[str, UUID],
    authority: NorthstarAuthorityManifest,
    source_manifest_digest: str,
    base_company_revision: int,
    frozen_at: datetime,
    profiles: tuple[PlanningResourceProfile, ...],
    busy_intervals: tuple[tuple[UUID, datetime, datetime, str], ...],
) -> PlanningSnapshot:
    """Fail closed on omitted work, changed authority or unsupported live constraints."""
    admission = admit_live_northstar_contract(
        company_id=company_id,
        request_id=request_id,
        contract=contract,
        source_version_ids=source_version_ids,
        authority=authority,
    )
    if admission.status != "admitted":
        raise MaterializationError(admission.issues[0].message)
    actual_tasks = {item.task_key: item for item in contract.tasks}

    base = build_northstar_snapshot(
        company_id=company_id,
        run_id=run_id,
        request_id=request_id,
        candidate_contract_id=candidate_contract_id,
        source_version_ids=source_version_ids,
        source_manifest_digest=source_manifest_digest,
        base_company_revision=base_company_revision,
        frozen_at=frozen_at,
        permission_revision="northstar-operator-authority.v1",
        profile_revision="live-profiles:"
        + str(max((profile.profile_revision for profile in profiles), default=0)),
    )
    zone = ZoneInfo(NORTHSTAR_TIMEZONE)
    origin = base.horizon_start.astimezone(UTC)

    def slot(instant: datetime) -> int:
        minutes = (instant.astimezone(UTC) - origin).total_seconds() / 60
        if instant.utcoffset() is None or minutes % base.slot_minutes:
            raise MaterializationError("live capacity must use exact offset-aware aligned instants")
        return int(minutes / base.slot_minutes)

    resources = {
        person_id(company_id, key): key
        for task in authority.tasks
        for key in task.eligible_person_keys
    }
    selected_profiles = {
        profile.resource_id: profile for profile in profiles if profile.resource_id in resources
    }
    if selected_profiles.keys() != resources.keys():
        raise MaterializationError(
            "a required owner or reviewer has no active authoritative profile"
        )
    constraints = []
    by_id = {task_id(run_id, key): task for key, task in actual_tasks.items()}
    for constraint in base.constraints:
        payload = constraint.payload
        if isinstance(payload, ResourceCapacityPayload):
            profile = selected_profiles[payload.resource_id]
            allowed = tuple(
                sorted(
                    {
                        index
                        for window in profile.availability
                        for index in range(
                            max(0, slot(window.start_at)), min(base.slot_count, slot(window.end_at))
                        )
                    }
                )
            )
            # The operator's no-overtime authority remains a ceiling even if a profile widens.
            if not allowed or not set(allowed) <= set(payload.available_slots):
                raise MaterializationError(
                    "live working profile exceeds the admitted no-overtime domain"
                )
            if (
                profile.timezone != authority.timezone
                or profile.daily_active_minutes % base.slot_minutes
            ):
                raise MaterializationError(
                    "live profile timezone or daily capacity cannot be represented exactly"
                )
            days = sorted(
                {
                    (
                        (origin + timedelta(minutes=index * base.slot_minutes))
                        .astimezone(zone)
                        .date()
                        - base.horizon_start.astimezone(zone).date()
                    ).days
                    for index in allowed
                }
            )
            payload = ResourceCapacityPayload(
                family="resource_capacity",
                resource_id=payload.resource_id,
                resource_kind="human",
                timezone=profile.timezone,
                available_slots=allowed,
                capacity_per_slot=1,
                daily_budgets=tuple(
                    DailyBudget(
                        day_index=day, max_active_slots=min(28, profile.daily_active_minutes // 15)
                    )
                    for day in days
                ),
                capability_keys=profile.capability_keys,
                permission_keys=profile.permission_keys,
            )
            if (
                "northstar." + resources[payload.resource_id] not in profile.capability_keys
                or "northstar.launch" not in profile.permission_keys
            ):
                raise MaterializationError(
                    "current profile no longer grants its admitted launch eligibility"
                )
        elif isinstance(payload, TaskDefinitionPayload):
            payload = payload.model_copy(update={"title": by_id[payload.task_id].title})
        elif isinstance(payload, WorkingWindowPayload) and payload.task_id != task_id(run_id, "l1"):
            # Do not copy any authored P1 day or slot into a live choice domain.
            payload = payload.model_copy(update={"release_slot": 0, "end_slot": base.slot_count})
        elif isinstance(payload, ReservationPayload):
            continue  # Real current calendar/commitment facts are inserted below.
        constraints.append(constraint.model_copy(update={"payload": payload}))
    protected_found = False
    relevant_busy_intervals = sorted(
        (item for item in busy_intervals if item[0] in resources),
        key=lambda item: (str(item[0]), item[1], item[2], item[3]),
    )
    for index, (resource_id, start, end, reference) in enumerate(relevant_busy_intervals):
        start_slot, end_slot = max(0, slot(start)), min(base.slot_count, slot(end))
        if end_slot <= start_slot:
            continue
        if (
            resource_id == person_id(company_id, "priya")
            and start.astimezone(zone) == datetime(2026, 9, 29, 11, tzinfo=zone)
            and end.astimezone(zone) == datetime(2026, 9, 29, 12, tzinfo=zone)
        ):
            protected_found = True
        template = next(
            rule for rule in base.constraints if rule.constraint_id == "protected.priya.tuesday"
        )
        constraints.append(
            template.model_copy(
                update={
                    "constraint_id": f"live.reservation.{index}",
                    "payload": ReservationPayload(
                        family="reservation",
                        resource_id=resource_id,
                        reservation_ref=reference,
                        slots=tuple(range(start_slot, end_slot)),
                        capacity_units=1,
                        consumes_daily_budget=True,
                    ),
                }
            )
        )
    if not protected_found:
        raise MaterializationError("the scenario's protected current capacity fact is missing")
    return PlanningSnapshot.freeze(
        **{
            **base.model_dump(exclude={"snapshot_digest", "constraints", "policy"}),
            "constraints": tuple(constraints),
            "policy": PlanningPolicy(
                policy_version=NORTHSTAR_SCENARIO_VERSION + ".live",
                timeout_ms=10000,
                resource_limit=1000000,
                allow_authorized_repair=False,
                max_repair_attempts=0,
            ),
        }
    )
