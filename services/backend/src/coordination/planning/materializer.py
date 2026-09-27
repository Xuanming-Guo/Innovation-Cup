from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coordination.interpretation.contracts import (
    AssumptionBasis,
    CandidateBasis,
    CandidateDependency,
    CandidateTask,
    CandidateTaskContract,
    ClarificationBasis,
    EvidenceBasis,
)
from coordination.planning.contracts import (
    DailyBudget,
    DeadlinePayload,
    DependencyPayload,
    EffortPayload,
    EligibilityPayload,
    MovementPayload,
    PlanningPolicy,
    PlanningSnapshot,
    PriorityPayload,
    ResourceCapacityPayload,
    SegmentationPayload,
    TaskDefinitionPayload,
    ValidatedConstraint,
    WorkingWindowPayload,
)
from coordination.planning.fixed_verifier import FIXED_COMPILER_VERSION

MATERIALIZER_VERSION = "coordination-candidate-materializer.v1"


class MaterializationError(ValueError):
    """The admitted candidate cannot be represented by the trusted planning model."""


class StrictMaterializationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AvailabilityWindow(StrictMaterializationModel):
    start_at: datetime
    end_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("availability timestamps must include a UTC offset")
        return value

    @model_validator(mode="after")
    def positive(self) -> AvailabilityWindow:
        if self.end_at <= self.start_at:
            raise ValueError("availability window must have positive width")
        return self


class PlanningResourceProfile(StrictMaterializationModel):
    resource_id: UUID
    timezone: str = Field(min_length=1, max_length=64)
    availability: tuple[AvailabilityWindow, ...] = Field(min_length=1, max_length=500)
    capability_keys: tuple[str, ...] = Field(max_length=200)
    permission_keys: tuple[str, ...] = Field(max_length=200)
    daily_active_minutes: int = Field(ge=0, le=1_440)
    profile_revision: int = Field(gt=0)
    estimate_revision: int = Field(gt=0)

    @model_validator(mode="after")
    def canonical(self) -> PlanningResourceProfile:
        if tuple(sorted(self.availability, key=lambda item: item.start_at)) != self.availability:
            raise ValueError("availability windows must be ordered")
        if any(
            left.end_at > right.start_at
            for left, right in zip(self.availability, self.availability[1:], strict=False)
        ):
            raise ValueError("availability windows must not overlap")
        if tuple(sorted(set(self.capability_keys))) != self.capability_keys:
            raise ValueError("capability keys must be unique and ordered")
        if tuple(sorted(set(self.permission_keys))) != self.permission_keys:
            raise ValueError("permission keys must be unique and ordered")
        return self


class MaterializationInput(StrictMaterializationModel):
    candidate_contract_id: UUID
    contract: CandidateTaskContract
    source_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_source_version_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)
    base_company_revision: int = Field(ge=0)
    policy_revision: int = Field(ge=0)
    requested_priority_key: str | None
    requester_membership_id: UUID
    resources: tuple[PlanningResourceProfile, ...] = Field(min_length=1, max_length=500)
    frozen_at: datetime
    slot_minutes: int = Field(default=15, ge=5, le=240)

    @field_validator("frozen_at")
    @classmethod
    def frozen_at_is_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("frozen_at must include a UTC offset")
        return value


def _source_ids(bases: tuple[CandidateBasis, ...]) -> tuple[UUID, ...]:
    if any(isinstance(basis, AssumptionBasis) for basis in bases):
        raise MaterializationError("planning constraints require confirmed bases")
    source_ids = {basis.source_version_id for basis in bases if isinstance(basis, EvidenceBasis)}
    return tuple(sorted(source_ids, key=str))


def _clarification_authority_refs(bases: tuple[CandidateBasis, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                f"clarification-response:{basis.response_id}"
                for basis in bases
                if isinstance(basis, ClarificationBasis)
            }
        )
    )


def _constraint(
    *,
    constraint_id: str,
    company_id: UUID,
    payload: object,
    source_version_ids: tuple[UUID, ...] = (),
    authority_refs: tuple[str, ...] = (),
    strength: Literal["hard", "preferred"] = "hard",
    negotiability: Literal["locked", "authorized", "preferred"] = "locked",
) -> ValidatedConstraint:
    return ValidatedConstraint.model_validate(
        {
            "constraint_id": constraint_id,
            "company_id": company_id,
            "strength": strength,
            "payload": payload,
            "source_version_ids": tuple(sorted(set(source_version_ids), key=str)),
            "authority_refs": tuple(sorted(set(authority_refs))),
            "confidentiality": "company",
            "negotiability": negotiability,
            "confirmation": "confirmed",
        }
    )


def _deadline_slot(deadline: datetime, horizon_start: datetime, slot_minutes: int) -> int:
    elapsed = (deadline.astimezone(UTC) - horizon_start).total_seconds() / 60
    if elapsed <= 0:
        raise MaterializationError("candidate deadline precedes the planning horizon")
    if elapsed % slot_minutes:
        raise MaterializationError("deadline must align exactly to the planning granularity")
    return int(elapsed // slot_minutes)


def _priority_tier(value: str | None) -> int:
    tiers = {"critical": 0, "urgent": 0, "high": 2, "normal": 5, "low": 8}
    return tiers.get((value or "normal").strip().lower(), 5)


def _task_eligibility(
    task: CandidateTask, resources: tuple[PlanningResourceProfile, ...]
) -> tuple[UUID, ...]:
    hard_capabilities = {
        requirement.requirement_key
        for requirement in task.requirements
        if requirement.strength == "hard" and requirement.kind in {"skill", "qualification", "tool"}
    }
    hard_permissions = {
        requirement.requirement_key
        for requirement in task.requirements
        if requirement.strength == "hard" and requirement.kind in {"permission", "input"}
    }
    unsupported = [
        requirement.requirement_key
        for requirement in task.requirements
        if requirement.strength == "hard" and requirement.kind == "review"
    ]
    if unsupported:
        raise MaterializationError("review requirements need an explicit review task")
    eligible = tuple(
        sorted(
            (
                profile.resource_id
                for profile in resources
                if hard_capabilities.issubset(profile.capability_keys)
                and hard_permissions.issubset(profile.permission_keys)
            ),
            key=str,
        )
    )
    if not eligible:
        raise MaterializationError(f"task {task.task_key} has no eligible resource")
    return eligible


def _availability_slots(
    profile: PlanningResourceProfile,
    horizon_start: datetime,
    horizon_end: datetime,
    slot_minutes: int,
) -> tuple[int, ...]:
    slots: set[int] = set()
    total_slots = int((horizon_end - horizon_start).total_seconds() // (slot_minutes * 60))
    for window in profile.availability:
        start_minutes = (window.start_at.astimezone(UTC) - horizon_start).total_seconds() / 60
        end_minutes = (window.end_at.astimezone(UTC) - horizon_start).total_seconds() / 60
        if start_minutes % slot_minutes or end_minutes % slot_minutes:
            raise MaterializationError("resource availability must align to the planning slot size")
        first = max(0, int(start_minutes // slot_minutes))
        last = min(total_slots, int(end_minutes // slot_minutes))
        slots.update(range(first, last))
    result = tuple(sorted(slots))
    if not result:
        raise MaterializationError("resource has no availability inside the planning horizon")
    return result


def _dependency_constraint(
    dependency: CandidateDependency,
    *,
    company_id: UUID,
    task_ids: dict[str, UUID],
    slot_minutes: int,
) -> ValidatedConstraint:
    if dependency.dependency_type == "information":
        raise MaterializationError("information dependencies need an explicit confirmed handoff")
    if dependency.minimum_lag_minutes % slot_minutes:
        raise MaterializationError("dependency lag must align exactly to the planning granularity")
    lag_slots = dependency.minimum_lag_minutes // slot_minutes
    return _constraint(
        constraint_id=(
            f"dependency.{dependency.predecessor_task_key}.{dependency.successor_task_key}"
        ),
        company_id=company_id,
        payload=DependencyPayload(
            family="dependency_lag",
            predecessor_task_id=task_ids[dependency.predecessor_task_key],
            successor_task_id=task_ids[dependency.successor_task_key],
            minimum_lag_slots=lag_slots,
            acceptance_required=dependency.dependency_type == "acceptance_to_start",
        ),
        source_version_ids=_source_ids(dependency.bases),
        authority_refs=_clarification_authority_refs(dependency.bases),
    )


def materialize_candidate(value: MaterializationInput) -> PlanningSnapshot:
    contract = value.contract
    if not contract.tasks:
        raise MaterializationError("candidate contains no schedulable tasks")
    selected_sources = set(value.selected_source_version_ids)
    if not selected_sources:
        raise MaterializationError("planning requires a current source manifest")
    if any(task.timing_type != "flexible_active" for task in contract.tasks):
        raise MaterializationError("candidate timing requires fields not present in this schema")

    horizon_start = min(
        window.start_at.astimezone(UTC)
        for profile in value.resources
        for window in profile.availability
    )
    horizon_end = max(
        window.end_at.astimezone(UTC)
        for profile in value.resources
        for window in profile.availability
    )
    if horizon_end <= horizon_start:
        raise MaterializationError("planning resources do not define a usable horizon")

    authority = f"requester-membership:{value.requester_membership_id}"
    policy_authority = f"company-policy-revision:{value.policy_revision}"
    task_ids = {
        task.task_key: uuid5(value.candidate_contract_id, f"task:{task.task_key}")
        for task in contract.tasks
    }
    constraints: list[ValidatedConstraint] = []

    for profile in value.resources:
        available_slots = _availability_slots(
            profile, horizon_start, horizon_end, value.slot_minutes
        )
        day_indexes = sorted({slot * value.slot_minutes // 1_440 for slot in available_slots})
        daily_slots = profile.daily_active_minutes // value.slot_minutes
        constraints.append(
            _constraint(
                constraint_id=f"resource.{profile.resource_id.hex}.capacity",
                company_id=contract.company_id,
                payload=ResourceCapacityPayload(
                    family="resource_capacity",
                    resource_id=profile.resource_id,
                    resource_kind="human",
                    timezone=profile.timezone,
                    available_slots=available_slots,
                    capacity_per_slot=1,
                    daily_budgets=tuple(
                        DailyBudget(day_index=day_index, max_active_slots=daily_slots)
                        for day_index in day_indexes
                    ),
                    capability_keys=profile.capability_keys,
                    permission_keys=profile.permission_keys,
                ),
                authority_refs=(
                    f"resource-profile:{profile.resource_id}:{profile.profile_revision}",
                    policy_authority,
                ),
            )
        )

    for task in contract.tasks:
        task_id = task_ids[task.task_key]
        task_sources = _source_ids(task.bases)
        estimate_sources = _source_ids(task.estimate.bases)
        task_authority_refs = _clarification_authority_refs(task.bases)
        estimate_authority_refs = _clarification_authority_refs(task.estimate.bases)
        if not set(task_sources + estimate_sources).issubset(selected_sources):
            raise MaterializationError("candidate basis is outside the selected source manifest")
        deadline_slot = (
            _deadline_slot(task.deadline.requested_at, horizon_start, value.slot_minutes)
            if task.deadline is not None
            else int((horizon_end - horizon_start).total_seconds() // (value.slot_minutes * 60))
        )
        horizon_slots = int(
            (horizon_end - horizon_start).total_seconds() // (value.slot_minutes * 60)
        )
        if deadline_slot > horizon_slots:
            raise MaterializationError("candidate deadline exceeds the planning horizon")
        if task.estimate.active_minutes % value.slot_minutes:
            raise MaterializationError(
                "active effort must align exactly to the planning granularity"
            )
        effort_slots = task.estimate.active_minutes // value.slot_minutes
        eligible = _task_eligibility(task, value.resources)
        requirement_sources = tuple(
            sorted(
                {
                    source_id
                    for requirement in task.requirements
                    for source_id in _source_ids(requirement.bases)
                },
                key=str,
            )
        )
        requirement_authority_refs = tuple(
            sorted(
                {
                    authority_ref
                    for requirement in task.requirements
                    for authority_ref in _clarification_authority_refs(requirement.bases)
                }
            )
        )
        if not set(requirement_sources).issubset(selected_sources):
            raise MaterializationError("candidate requirement is outside the source manifest")

        constraints.extend(
            (
                _constraint(
                    constraint_id=f"task.{task.task_key}.definition",
                    company_id=contract.company_id,
                    payload=TaskDefinitionPayload(
                        family="task_definition",
                        task_id=task_id,
                        task_key=task.task_key,
                        title=task.title,
                        scheduling_kind=task.timing_type,
                    ),
                    source_version_ids=task_sources,
                    authority_refs=task_authority_refs,
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.effort",
                    company_id=contract.company_id,
                    payload=EffortPayload(
                        family="effort",
                        task_id=task_id,
                        active_slots=effort_slots,
                        elapsed_slots=effort_slots,
                    ),
                    source_version_ids=estimate_sources,
                    authority_refs=estimate_authority_refs,
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.eligibility",
                    company_id=contract.company_id,
                    payload=EligibilityPayload(
                        family="eligibility",
                        task_id=task_id,
                        allowed_resource_ids=eligible,
                    ),
                    source_version_ids=requirement_sources or task_sources,
                    authority_refs=tuple(
                        sorted(
                            set(requirement_authority_refs)
                            | {f"resource-profile:{resource_id}" for resource_id in eligible}
                        )
                    ),
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.window",
                    company_id=contract.company_id,
                    payload=WorkingWindowPayload(
                        family="working_window",
                        task_id=task_id,
                        release_slot=0,
                        end_slot=deadline_slot,
                    ),
                    source_version_ids=task_sources,
                    authority_refs=tuple(sorted({authority, *task_authority_refs})),
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.deadline",
                    company_id=contract.company_id,
                    payload=DeadlinePayload(
                        family="deadline",
                        task_id=task_id,
                        requested_finish_slot=deadline_slot,
                        hard_finish_slot=(
                            deadline_slot
                            if task.deadline is not None and task.deadline.flexibility == "fixed"
                            else None
                        ),
                        max_authorized_finish_slot=deadline_slot,
                    ),
                    source_version_ids=(
                        _source_ids(task.deadline.bases)
                        if task.deadline is not None
                        else task_sources
                    ),
                    authority_refs=tuple(
                        sorted(
                            {
                                authority,
                                *(
                                    _clarification_authority_refs(task.deadline.bases)
                                    if task.deadline is not None
                                    else task_authority_refs
                                ),
                            }
                        )
                    ),
                    negotiability=(
                        "locked"
                        if task.deadline is not None and task.deadline.flexibility == "fixed"
                        else "authorized"
                    ),
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.priority",
                    company_id=contract.company_id,
                    payload=PriorityPayload(
                        family="priority",
                        task_id=task_id,
                        tier=_priority_tier(value.requested_priority_key),
                    ),
                    authority_refs=(authority, policy_authority),
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.segmentation",
                    company_id=contract.company_id,
                    payload=SegmentationPayload(
                        family="segmentation",
                        task_id=task_id,
                        split_allowed=False,
                        minimum_segment_slots=effort_slots,
                        max_segments_per_day=1,
                    ),
                    authority_refs=(policy_authority,),
                ),
                _constraint(
                    constraint_id=f"task.{task.task_key}.movement",
                    company_id=contract.company_id,
                    payload=MovementPayload(
                        family="movement",
                        task_id=task_id,
                        movement="new",
                        existing_resource_id=None,
                        existing_slots=(),
                    ),
                    authority_refs=(authority,),
                ),
            )
        )

    constraints.extend(
        _dependency_constraint(
            dependency,
            company_id=contract.company_id,
            task_ids=task_ids,
            slot_minutes=value.slot_minutes,
        )
        for dependency in contract.dependencies
    )

    profile_revision = max(profile.profile_revision for profile in value.resources)
    estimate_revision = max(profile.estimate_revision for profile in value.resources)
    return PlanningSnapshot.freeze(
        snapshot_id=uuid5(value.candidate_contract_id, "planning-snapshot:v1"),
        company_id=contract.company_id,
        request_id=contract.request_id,
        candidate_contract_id=value.candidate_contract_id,
        base_company_revision=value.base_company_revision,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        slot_minutes=value.slot_minutes,
        source_manifest_digest=value.source_manifest_digest,
        permission_revision=f"policy:{value.policy_revision}",
        profile_revision=f"profiles:{profile_revision}",
        estimate_revision=f"estimates:{estimate_revision}",
        compiler_version=FIXED_COMPILER_VERSION,
        policy=PlanningPolicy(
            policy_version="alto-fixed-planning-policy.v1",
            timeout_ms=5_000,
            resource_limit=2_000_000,
            allow_authorized_repair=False,
            max_repair_attempts=0,
        ),
        constraints=tuple(constraints),
        frozen_at=value.frozen_at,
    )
