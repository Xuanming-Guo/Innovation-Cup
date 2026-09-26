from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

ConstraintStrength = Literal["hard", "preferred"]
SchedulingKind = Literal["flexible_active", "review", "fixed_attendance", "passive_wait"]
PlanningScope = Literal["pinned_insertion", "authorized_repair"]
ResultClassification = Literal[
    "OPTIMAL_WITHIN_MODEL",
    "FEASIBLE",
    "INFEASIBLE_WITHIN_SCOPE",
    "UNKNOWN_OR_TIMEOUT",
    "INVALID_INPUT",
]


class StrictPlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DailyBudget(StrictPlanningModel):
    day_index: int = Field(ge=0, le=366)
    max_active_slots: int = Field(ge=0, le=10_000)


class SharedResourceDemand(StrictPlanningModel):
    resource_id: UUID
    capacity_units: int = Field(ge=1, le=16)


class TaskDefinitionPayload(StrictPlanningModel):
    family: Literal["task_definition"]
    task_id: UUID
    task_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=160)
    scheduling_kind: SchedulingKind


class ResourceCapacityPayload(StrictPlanningModel):
    family: Literal["resource_capacity"]
    resource_id: UUID
    resource_kind: Literal["human", "shared"]
    timezone: str = Field(min_length=1, max_length=64)
    available_slots: tuple[int, ...] = Field(max_length=20_000)
    capacity_per_slot: int = Field(ge=1, le=16)
    daily_budgets: tuple[DailyBudget, ...] = Field(max_length=367)
    capability_keys: tuple[str, ...] = Field(max_length=200)
    permission_keys: tuple[str, ...] = Field(max_length=200)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @model_validator(mode="after")
    def canonical_resource(self) -> Self:
        if tuple(sorted(set(self.available_slots))) != self.available_slots:
            raise ValueError("available_slots must be unique and sorted")
        if (
            len({item.day_index for item in self.daily_budgets}) != len(self.daily_budgets)
            or tuple(sorted(self.daily_budgets, key=lambda item: item.day_index))
            != self.daily_budgets
        ):
            raise ValueError("daily budgets must have unique, ordered day indexes")
        if tuple(sorted(set(self.capability_keys))) != self.capability_keys:
            raise ValueError("capability keys must be unique and sorted")
        if tuple(sorted(set(self.permission_keys))) != self.permission_keys:
            raise ValueError("permission keys must be unique and sorted")
        return self


class EffortPayload(StrictPlanningModel):
    family: Literal["effort"]
    task_id: UUID
    active_slots: int = Field(ge=0, le=20_000)
    elapsed_slots: int = Field(ge=1, le=20_000)


class EligibilityPayload(StrictPlanningModel):
    family: Literal["eligibility"]
    task_id: UUID
    allowed_resource_ids: tuple[UUID, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_resources(self) -> Self:
        if tuple(sorted(set(self.allowed_resource_ids), key=str)) != self.allowed_resource_ids:
            raise ValueError("eligible resources must be unique and sorted")
        return self


class WorkingWindowPayload(StrictPlanningModel):
    family: Literal["working_window"]
    task_id: UUID
    release_slot: int = Field(ge=0)
    end_slot: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        if self.end_slot <= self.release_slot:
            raise ValueError("working window must have positive width")
        return self


class FixedAttendancePayload(StrictPlanningModel):
    family: Literal["fixed_attendance"]
    task_id: UUID
    participant_resource_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    slots: tuple[int, ...] = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def canonical_attendance(self) -> Self:
        if (
            tuple(sorted(set(self.participant_resource_ids), key=str))
            != self.participant_resource_ids
        ):
            raise ValueError("fixed participants must be unique and sorted")
        if tuple(sorted(set(self.slots))) != self.slots:
            raise ValueError("fixed slots must be unique and sorted")
        return self


class DependencyPayload(StrictPlanningModel):
    family: Literal["dependency_lag"]
    predecessor_task_id: UUID
    successor_task_id: UUID
    minimum_lag_slots: int = Field(ge=0, le=20_000)
    acceptance_required: bool

    @model_validator(mode="after")
    def no_self_edge(self) -> Self:
        if self.predecessor_task_id == self.successor_task_id:
            raise ValueError("dependency cannot refer to the same task twice")
        return self


class ReviewPayload(StrictPlanningModel):
    family: Literal["acceptance_review"]
    review_task_id: UUID
    reviewed_task_id: UUID
    require_separate_resource: bool = True

    @model_validator(mode="after")
    def no_self_review(self) -> Self:
        if self.review_task_id == self.reviewed_task_id:
            raise ValueError("review task cannot review itself")
        return self


class DeadlinePayload(StrictPlanningModel):
    family: Literal["deadline"]
    task_id: UUID
    requested_finish_slot: int | None = Field(default=None, gt=0)
    agreed_finish_slot: int | None = Field(default=None, gt=0)
    forecast_finish_slot: int | None = Field(default=None, gt=0)
    hard_finish_slot: int | None = Field(default=None, gt=0)
    max_authorized_finish_slot: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def valid_flexibility(self) -> Self:
        if (
            self.hard_finish_slot is not None
            and self.max_authorized_finish_slot is not None
            and self.max_authorized_finish_slot < self.hard_finish_slot
        ):
            raise ValueError("authorized finish cannot precede the hard finish")
        return self


class PriorityPayload(StrictPlanningModel):
    family: Literal["priority"]
    task_id: UUID
    tier: int = Field(ge=0, le=9)


class ReservationPayload(StrictPlanningModel):
    family: Literal["reservation"]
    resource_id: UUID
    reservation_ref: str = Field(min_length=1, max_length=200)
    slots: tuple[int, ...] = Field(min_length=1, max_length=20_000)
    capacity_units: int = Field(ge=1, le=16)
    consumes_daily_budget: bool = True

    @model_validator(mode="after")
    def canonical_slots(self) -> Self:
        if tuple(sorted(set(self.slots))) != self.slots:
            raise ValueError("reservation slots must be unique and sorted")
        return self


class SharedResourcePayload(StrictPlanningModel):
    family: Literal["shared_resource"]
    task_id: UUID
    demands: tuple[SharedResourceDemand, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_resources(self) -> Self:
        if (
            len({item.resource_id for item in self.demands}) != len(self.demands)
            or tuple(sorted(self.demands, key=lambda item: str(item.resource_id))) != self.demands
        ):
            raise ValueError("shared resource demands must be unique and sorted")
        return self


class SegmentationPayload(StrictPlanningModel):
    family: Literal["segmentation"]
    task_id: UUID
    split_allowed: bool
    minimum_segment_slots: int = Field(ge=1, le=20_000)
    max_segments_per_day: int = Field(ge=1, le=100)


class MovementPayload(StrictPlanningModel):
    family: Literal["movement"]
    task_id: UUID
    movement: Literal["new", "locked", "authorized"]
    existing_resource_id: UUID | None = None
    existing_slots: tuple[int, ...] = Field(max_length=20_000)

    @model_validator(mode="after")
    def valid_existing_assignment(self) -> Self:
        has_existing = self.existing_resource_id is not None or bool(self.existing_slots)
        if self.movement == "new" and has_existing:
            raise ValueError("new work cannot contain an existing assignment")
        if self.movement != "new" and (
            self.existing_resource_id is None or not self.existing_slots
        ):
            raise ValueError("existing work requires an owner and occupied slots")
        if tuple(sorted(set(self.existing_slots))) != self.existing_slots:
            raise ValueError("existing slots must be unique and sorted")
        return self


ConstraintPayload = Annotated[
    TaskDefinitionPayload
    | ResourceCapacityPayload
    | EffortPayload
    | EligibilityPayload
    | WorkingWindowPayload
    | FixedAttendancePayload
    | DependencyPayload
    | ReviewPayload
    | DeadlinePayload
    | PriorityPayload
    | ReservationPayload
    | SharedResourcePayload
    | SegmentationPayload
    | MovementPayload,
    Field(discriminator="family"),
]


class ValidatedConstraint(StrictPlanningModel):
    schema_version: Literal["validated-constraint.v1"] = "validated-constraint.v1"
    constraint_id: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")
    company_id: UUID
    strength: ConstraintStrength
    payload: ConstraintPayload
    source_version_ids: tuple[UUID, ...] = Field(max_length=50)
    authority_refs: tuple[str, ...] = Field(max_length=50)
    confidentiality: Literal["company", "restricted"] = "company"
    negotiability: Literal["locked", "authorized", "preferred"]
    confirmation: Literal["confirmed"] = "confirmed"

    @model_validator(mode="after")
    def has_authoritative_basis(self) -> Self:
        if not self.source_version_ids and not self.authority_refs:
            raise ValueError("validated constraint requires evidence or an authority reference")
        if self.strength == "hard" and self.negotiability == "preferred":
            raise ValueError("hard constraints cannot be marked preferred")
        if self.strength == "preferred" and self.negotiability == "locked":
            raise ValueError("preferred constraints cannot be marked locked")
        if tuple(sorted(set(self.source_version_ids), key=str)) != self.source_version_ids:
            raise ValueError("source version IDs must be unique and sorted")
        if tuple(sorted(set(self.authority_refs))) != self.authority_refs:
            raise ValueError("authority references must be unique and sorted")
        return self


class PlanningPolicy(StrictPlanningModel):
    policy_version: str = Field(min_length=1, max_length=120)
    timeout_ms: int = Field(ge=10, le=120_000)
    resource_limit: int = Field(ge=1_000, le=2_000_000_000)
    allow_authorized_repair: bool
    max_repair_attempts: int = Field(ge=0, le=2)
    max_tasks: int = Field(default=200, ge=1, le=2_000)
    max_resources: int = Field(default=500, ge=1, le=5_000)
    max_slots: int = Field(default=2_000, ge=1, le=20_000)
    max_boolean_variables: int = Field(default=2_000_000, ge=1_000, le=20_000_000)

    @model_validator(mode="after")
    def repair_policy_is_bounded(self) -> Self:
        if not self.allow_authorized_repair and self.max_repair_attempts != 0:
            raise ValueError("disabled repair must have zero repair attempts")
        return self


def canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PlanningSnapshot(StrictPlanningModel):
    schema_version: Literal["planning-snapshot.v1"] = "planning-snapshot.v1"
    snapshot_id: UUID
    company_id: UUID
    request_id: UUID
    candidate_contract_id: UUID
    base_company_revision: int = Field(ge=0)
    horizon_start: datetime
    horizon_end: datetime
    slot_minutes: int = Field(ge=5, le=240)
    source_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    permission_revision: str = Field(min_length=1, max_length=120)
    profile_revision: str = Field(min_length=1, max_length=120)
    estimate_revision: str = Field(min_length=1, max_length=120)
    compiler_version: str = Field(min_length=1, max_length=120)
    policy: PlanningPolicy
    constraints: tuple[ValidatedConstraint, ...] = Field(min_length=1, max_length=20_000)
    frozen_at: datetime
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("horizon_start", "horizon_end", "frozen_at")
    @classmethod
    def aware_datetime(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("planning timestamps must include a UTC offset")
        return value

    @model_validator(mode="after")
    def valid_snapshot(self, info: ValidationInfo) -> Self:
        start = self.horizon_start.astimezone(UTC)
        end = self.horizon_end.astimezone(UTC)
        if end <= start:
            raise ValueError("planning horizon must have positive width")
        seconds = int((end - start).total_seconds())
        if seconds % (self.slot_minutes * 60) != 0:
            raise ValueError("planning horizon must align to whole slots")
        if self.slot_count > self.policy.max_slots:
            raise ValueError("planning horizon exceeds the configured slot limit")
        ids = [constraint.constraint_id for constraint in self.constraints]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("constraints must have unique IDs in canonical order")
        if any(constraint.company_id != self.company_id for constraint in self.constraints):
            raise ValueError("all constraints must belong to the snapshot company")
        if not (info.context or {}).get("skip_digest") and self.snapshot_digest != canonical_digest(
            self.digest_payload()
        ):
            raise ValueError("snapshot digest does not match canonical contents")
        return self

    @property
    def slot_count(self) -> int:
        return int(
            (self.horizon_end.astimezone(UTC) - self.horizon_start.astimezone(UTC)).total_seconds()
            // (self.slot_minutes * 60)
        )

    def digest_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"snapshot_digest"})

    @classmethod
    def freeze(cls, **values: object) -> PlanningSnapshot:
        raw_constraints = values.get("constraints")
        if not isinstance(raw_constraints, (tuple, list)):
            raise ValueError("constraints are required")
        constraints = tuple(sorted(raw_constraints, key=lambda item: str(item.constraint_id)))
        values["constraints"] = constraints
        serializable = cls.model_validate(
            {**values, "snapshot_digest": "0" * 64}, context={"skip_digest": True}
        )
        digest_payload = serializable.model_dump(mode="json", exclude={"snapshot_digest"})
        values["snapshot_digest"] = canonical_digest(digest_payload)
        return cls.model_validate(values)


class CompiledModel(StrictPlanningModel):
    schema_version: Literal["compiled-model.v1"] = "compiled-model.v1"
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiler_version: str
    scope: PlanningScope
    constraint_ids: tuple[str, ...]
    task_count: int = Field(ge=0)
    resource_count: int = Field(ge=0)
    slot_count: int = Field(ge=1)
    boolean_variable_count: int = Field(ge=0)


class TaskPlacement(StrictPlanningModel):
    task_id: UUID
    start_slot: int = Field(ge=0)
    end_slot: int = Field(gt=0)
    owner_resource_id: UUID | None


class ScheduleBlock(StrictPlanningModel):
    task_id: UUID
    resource_id: UUID
    start_slot: int = Field(ge=0)
    end_slot: int = Field(gt=0)
    capacity_units: int = Field(ge=1, le=16)
    role: Literal["owner", "participant", "shared"]


class ObjectiveValue(StrictPlanningModel):
    name: str = Field(min_length=1, max_length=120)
    value: int


class ValidationIssue(StrictPlanningModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    task_id: UUID | None = None
    resource_id: UUID | None = None
    constraint_ids: tuple[str, ...] = Field(max_length=100)


class ValidationReport(StrictPlanningModel):
    validator_version: str = Field(min_length=1, max_length=120)
    valid: bool
    schedule_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[ValidationIssue, ...]


class SolverAttempt(StrictPlanningModel):
    run_id: UUID
    scope: PlanningScope
    classification: ResultClassification
    raw_status: Literal["sat", "unsat", "unknown", "invalid"]
    termination: Literal["completed", "timeout", "resource_limit", "unknown", "invalid"]
    reason_unknown: str | None = Field(default=None, max_length=500)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model: CompiledModel | None
    solver_version: str
    runtime_ms: int = Field(ge=0)
    timeout_ms: int = Field(ge=1)
    resource_limit: int = Field(ge=1)
    objectives: tuple[ObjectiveValue, ...]
    placements: tuple[TaskPlacement, ...]
    blocks: tuple[ScheduleBlock, ...]
    diagnostic_constraint_ids: tuple[str, ...]
    validation: ValidationReport | None


class PlanningDecision(StrictPlanningModel):
    schema_version: Literal["planning-decision.v1"] = "planning-decision.v1"
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: ResultClassification
    selected_attempt: int | None = Field(default=None, ge=0)
    attempts: tuple[SolverAttempt, ...] = Field(min_length=1, max_length=3)
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def record(
        cls,
        *,
        snapshot_digest: str,
        classification: ResultClassification,
        selected_attempt: int | None,
        attempts: tuple[SolverAttempt, ...],
    ) -> PlanningDecision:
        payload = {
            "schema_version": "planning-decision.v1",
            "snapshot_digest": snapshot_digest,
            "classification": classification,
            "selected_attempt": selected_attempt,
            "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
        }
        return cls(
            snapshot_digest=snapshot_digest,
            classification=classification,
            selected_attempt=selected_attempt,
            attempts=attempts,
            decision_digest=canonical_digest(payload),
        )
