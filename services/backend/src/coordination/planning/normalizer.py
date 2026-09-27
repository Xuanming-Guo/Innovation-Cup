from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from coordination.planning.contracts import (
    ActiveParticipantsPayload,
    DeadlinePayload,
    DependencyPayload,
    EffortPayload,
    EligibilityPayload,
    ExecutionGatePayload,
    FixedAttendancePayload,
    MovementPayload,
    PlanningSnapshot,
    PriorityPayload,
    ReservationPayload,
    ResourceCapacityPayload,
    ReviewPayload,
    SegmentationPayload,
    SharedResourceDemand,
    SharedResourcePayload,
    TaskDefinitionPayload,
    TaskReviewPolicyPayload,
    ValidationIssue,
    WorkingWindowPayload,
)


class PlanningInputError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        super().__init__("planning snapshot is invalid")
        self.issues = issues


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    resource_id: UUID
    resource_kind: str
    timezone: str
    available_slots: frozenset[int]
    capacity_per_slot: int
    daily_budgets: dict[int, int]
    capability_keys: frozenset[str]
    permission_keys: frozenset[str]
    constraint_id: str


@dataclass(frozen=True, slots=True)
class ReservationSpec:
    resource_id: UUID
    reservation_ref: str
    slots: tuple[int, ...]
    capacity_units: int
    consumes_daily_budget: bool
    constraint_id: str


@dataclass(frozen=True, slots=True)
class DependencySpec:
    predecessor_task_id: UUID
    successor_task_id: UUID
    minimum_lag_slots: int
    acceptance_required: bool
    constraint_id: str


@dataclass(frozen=True, slots=True)
class ReviewSpec:
    review_task_id: UUID
    reviewed_task_id: UUID
    require_separate_resource: bool
    constraint_id: str


@dataclass(slots=True)
class TaskSpec:
    task_id: UUID
    task_key: str
    title: str
    scheduling_kind: str
    definition_constraint_id: str
    active_slots: int | None = None
    elapsed_slots: int | None = None
    effort_constraint_id: str | None = None
    allowed_resource_ids: tuple[UUID, ...] | None = None
    eligibility_constraint_id: str | None = None
    release_slot: int | None = None
    window_end_slot: int | None = None
    window_constraint_id: str | None = None
    fixed_resource_ids: tuple[UUID, ...] = ()
    fixed_slots: tuple[int, ...] = ()
    fixed_constraint_id: str | None = None
    participant_resource_ids: tuple[UUID, ...] = ()
    participants_constraint_id: str | None = None
    deadline: DeadlinePayload | None = None
    deadline_constraint_id: str | None = None
    priority_tier: int = 5
    priority_constraint_id: str | None = None
    shared_demands: tuple[SharedResourceDemand, ...] = ()
    shared_constraint_id: str | None = None
    split_allowed: bool | None = None
    minimum_segment_slots: int | None = None
    max_segments_per_day: int | None = None
    segmentation_constraint_id: str | None = None
    movement: str | None = None
    existing_resource_id: UUID | None = None
    existing_slots: tuple[int, ...] = ()
    movement_constraint_id: str | None = None
    review_policy: TaskReviewPolicyPayload | None = None
    review_policy_constraint_id: str | None = None

    @property
    def constraint_ids(self) -> tuple[str, ...]:
        optional = (
            self.effort_constraint_id,
            self.eligibility_constraint_id,
            self.window_constraint_id,
            self.fixed_constraint_id,
            self.participants_constraint_id,
            self.deadline_constraint_id,
            self.priority_constraint_id,
            self.shared_constraint_id,
            self.segmentation_constraint_id,
            self.movement_constraint_id,
            self.review_policy_constraint_id,
        )
        return (self.definition_constraint_id, *(value for value in optional if value))


@dataclass(frozen=True, slots=True)
class NormalizedPlanningModel:
    snapshot: PlanningSnapshot
    resources: dict[UUID, ResourceSpec]
    tasks: dict[UUID, TaskSpec]
    reservations: tuple[ReservationSpec, ...]
    dependencies: tuple[DependencySpec, ...]
    reviews: tuple[ReviewSpec, ...]
    constraint_ids: tuple[str, ...]
    execution_gates: tuple[ExecutionGatePayload, ...] = ()


def _cycle_exists(
    tasks: set[UUID],
    dependencies: tuple[DependencySpec, ...],
    reviews: tuple[ReviewSpec, ...],
) -> bool:
    graph: dict[UUID, set[UUID]] = defaultdict(set)
    for dependency in dependencies:
        graph[dependency.predecessor_task_id].add(dependency.successor_task_id)
    for review in reviews:
        graph[review.reviewed_task_id].add(review.review_task_id)
    visiting: set[UUID] = set()
    visited: set[UUID] = set()

    def visit(task_id: UUID) -> bool:
        if task_id in visiting:
            return True
        if task_id in visited:
            return False
        visiting.add(task_id)
        if any(visit(successor) for successor in graph.get(task_id, set())):
            return True
        visiting.remove(task_id)
        visited.add(task_id)
        return False

    return any(visit(task_id) for task_id in tasks)


def normalize_snapshot(snapshot: PlanningSnapshot) -> NormalizedPlanningModel:
    issues: list[ValidationIssue] = []
    resources: dict[UUID, ResourceSpec] = {}
    tasks: dict[UUID, TaskSpec] = {}
    reservations: list[ReservationSpec] = []
    dependencies: list[DependencySpec] = []
    reviews: list[ReviewSpec] = []
    execution_gates: list[ExecutionGatePayload] = []

    def issue(
        code: str,
        message: str,
        *,
        task_id: UUID | None = None,
        resource_id: UUID | None = None,
        constraint_ids: tuple[str, ...] = (),
    ) -> None:
        issues.append(
            ValidationIssue(
                code=code,
                message=message,
                task_id=task_id,
                resource_id=resource_id,
                constraint_ids=constraint_ids,
            )
        )

    for constraint in snapshot.constraints:
        payload = constraint.payload
        constraint_id = constraint.constraint_id
        if isinstance(payload, TaskDefinitionPayload):
            if payload.task_id in tasks:
                issue(
                    "duplicate_task_definition",
                    "task has more than one definition",
                    task_id=payload.task_id,
                    constraint_ids=(constraint_id,),
                )
            else:
                tasks[payload.task_id] = TaskSpec(
                    task_id=payload.task_id,
                    task_key=payload.task_key,
                    title=payload.title,
                    scheduling_kind=payload.scheduling_kind,
                    definition_constraint_id=constraint_id,
                )
        elif isinstance(payload, ResourceCapacityPayload):
            if payload.resource_id in resources:
                issue(
                    "duplicate_resource_definition",
                    "resource has more than one capacity definition",
                    resource_id=payload.resource_id,
                    constraint_ids=(constraint_id,),
                )
                continue
            if len(payload.available_slots) != len(set(payload.available_slots)):
                issue(
                    "duplicate_available_slot",
                    "resource availability contains duplicate slots",
                    resource_id=payload.resource_id,
                    constraint_ids=(constraint_id,),
                )
            invalid_slots = [
                slot for slot in payload.available_slots if slot < 0 or slot >= snapshot.slot_count
            ]
            if invalid_slots:
                issue(
                    "availability_outside_horizon",
                    "resource availability falls outside the planning horizon",
                    resource_id=payload.resource_id,
                    constraint_ids=(constraint_id,),
                )
            budgets = {
                budget.day_index: budget.max_active_slots for budget in payload.daily_budgets
            }
            if len(budgets) != len(payload.daily_budgets):
                issue(
                    "duplicate_daily_budget",
                    "resource contains more than one budget for a day",
                    resource_id=payload.resource_id,
                    constraint_ids=(constraint_id,),
                )
            resources[payload.resource_id] = ResourceSpec(
                resource_id=payload.resource_id,
                resource_kind=payload.resource_kind,
                timezone=payload.timezone,
                available_slots=frozenset(payload.available_slots),
                capacity_per_slot=payload.capacity_per_slot,
                daily_budgets=budgets,
                capability_keys=frozenset(payload.capability_keys),
                permission_keys=frozenset(payload.permission_keys),
                constraint_id=constraint_id,
            )

    task_keys = [task.task_key for task in tasks.values()]
    if len(task_keys) != len(set(task_keys)):
        issue("duplicate_task_key", "task keys must be unique within a snapshot")

    singleton_families: dict[tuple[UUID, str], str] = {}

    def task_for(task_id: UUID, family: str, constraint_id: str) -> TaskSpec | None:
        task = tasks.get(task_id)
        if task is None:
            issue(
                "unknown_task",
                f"{family} constraint refers to an unknown task",
                task_id=task_id,
                constraint_ids=(constraint_id,),
            )
            return None
        key = (task_id, family)
        previous = singleton_families.get(key)
        if previous is not None:
            issue(
                "duplicate_task_constraint",
                f"task has more than one {family} constraint",
                task_id=task_id,
                constraint_ids=(previous, constraint_id),
            )
            return None
        singleton_families[key] = constraint_id
        return task

    for constraint in snapshot.constraints:
        payload = constraint.payload
        constraint_id = constraint.constraint_id
        if isinstance(payload, (TaskDefinitionPayload, ResourceCapacityPayload)):
            continue
        if isinstance(payload, EffortPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.active_slots = payload.active_slots
                task.elapsed_slots = payload.elapsed_slots
                task.effort_constraint_id = constraint_id
        elif isinstance(payload, EligibilityPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.allowed_resource_ids = payload.allowed_resource_ids
                task.eligibility_constraint_id = constraint_id
        elif isinstance(payload, WorkingWindowPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.release_slot = payload.release_slot
                task.window_end_slot = payload.end_slot
                task.window_constraint_id = constraint_id
        elif isinstance(payload, FixedAttendancePayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.fixed_resource_ids = payload.participant_resource_ids
                task.fixed_slots = payload.slots
                task.fixed_constraint_id = constraint_id
        elif isinstance(payload, ActiveParticipantsPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.participant_resource_ids = payload.participant_resource_ids
                task.participants_constraint_id = constraint_id
        elif isinstance(payload, DeadlinePayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.deadline = payload
                task.deadline_constraint_id = constraint_id
        elif isinstance(payload, PriorityPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.priority_tier = payload.tier
                task.priority_constraint_id = constraint_id
        elif isinstance(payload, SharedResourcePayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.shared_demands = payload.demands
                task.shared_constraint_id = constraint_id
        elif isinstance(payload, SegmentationPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.split_allowed = payload.split_allowed
                task.minimum_segment_slots = payload.minimum_segment_slots
                task.max_segments_per_day = payload.max_segments_per_day
                task.segmentation_constraint_id = constraint_id
        elif isinstance(payload, MovementPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.movement = payload.movement
                task.existing_resource_id = payload.existing_resource_id
                task.existing_slots = payload.existing_slots
                task.movement_constraint_id = constraint_id
        elif isinstance(payload, DependencyPayload):
            dependencies.append(
                DependencySpec(
                    predecessor_task_id=payload.predecessor_task_id,
                    successor_task_id=payload.successor_task_id,
                    minimum_lag_slots=payload.minimum_lag_slots,
                    acceptance_required=payload.acceptance_required,
                    constraint_id=constraint_id,
                )
            )
        elif isinstance(payload, ExecutionGatePayload):
            execution_gates.append(payload)
        elif isinstance(payload, TaskReviewPolicyPayload):
            task = task_for(payload.task_id, payload.family, constraint_id)
            if task:
                task.review_policy = payload
                task.review_policy_constraint_id = constraint_id
        elif isinstance(payload, ReviewPayload):
            reviews.append(
                ReviewSpec(
                    review_task_id=payload.review_task_id,
                    reviewed_task_id=payload.reviewed_task_id,
                    require_separate_resource=payload.require_separate_resource,
                    constraint_id=constraint_id,
                )
            )
        elif isinstance(payload, ReservationPayload):
            reservations.append(
                ReservationSpec(
                    resource_id=payload.resource_id,
                    reservation_ref=payload.reservation_ref,
                    slots=payload.slots,
                    capacity_units=payload.capacity_units,
                    consumes_daily_budget=payload.consumes_daily_budget,
                    constraint_id=constraint_id,
                )
            )

    if len(tasks) > snapshot.policy.max_tasks:
        issue("task_limit_exceeded", "snapshot exceeds the configured task limit")
    if len(resources) > snapshot.policy.max_resources:
        issue("resource_limit_exceeded", "snapshot exceeds the configured resource limit")

    for task in tasks.values():
        if task.participant_resource_ids:
            if task.scheduling_kind not in ("flexible_active", "review"):
                issue(
                    "unsupported_active_participants",
                    "active participants require active work",
                    task_id=task.task_id,
                    constraint_ids=task.constraint_ids,
                )
            for participant_id in task.participant_resource_ids:
                resource = resources.get(participant_id)
                if resource is None or resource.resource_kind != "human":
                    issue(
                        "invalid_active_participant",
                        "active participant must be a known human",
                        task_id=task.task_id,
                        resource_id=participant_id,
                        constraint_ids=task.constraint_ids,
                    )
        ids = task.constraint_ids
        if task.effort_constraint_id is None:
            issue(
                "missing_effort",
                "task is missing an effort constraint",
                task_id=task.task_id,
                constraint_ids=ids,
            )
        if task.window_constraint_id is None:
            issue(
                "missing_working_window",
                "task is missing a working window",
                task_id=task.task_id,
                constraint_ids=ids,
            )
        if task.movement_constraint_id is None:
            issue(
                "missing_movement",
                "task is missing movement authority",
                task_id=task.task_id,
                constraint_ids=ids,
            )
        if (
            task.release_slot is not None
            and task.window_end_slot is not None
            and task.window_end_slot > snapshot.slot_count
        ):
            issue(
                "window_outside_horizon",
                "task working window exceeds the horizon",
                task_id=task.task_id,
                constraint_ids=ids,
            )
        if task.scheduling_kind in ("flexible_active", "review"):
            if task.active_slots is not None and task.active_slots <= 0:
                issue(
                    "non_positive_active_effort",
                    "active task requires positive effort",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if not task.allowed_resource_ids:
                issue(
                    "empty_eligibility",
                    "active task requires at least one eligible resource",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.segmentation_constraint_id is None:
                issue(
                    "missing_segmentation",
                    "active task is missing segmentation policy",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
        elif task.scheduling_kind == "fixed_attendance":
            if not task.fixed_slots or not task.fixed_resource_ids:
                issue(
                    "missing_fixed_attendance",
                    "fixed task requires participants and slots",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.active_slots is not None and task.active_slots != len(task.fixed_slots):
                issue(
                    "fixed_effort_mismatch",
                    "fixed task effort must match its fixed slots",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.fixed_slots and tuple(sorted(set(task.fixed_slots))) != task.fixed_slots:
                issue(
                    "invalid_fixed_slots",
                    "fixed slots must be unique and sorted",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.fixed_slots and task.fixed_slots != tuple(
                range(task.fixed_slots[0], task.fixed_slots[-1] + 1)
            ):
                issue(
                    "fragmented_fixed_attendance",
                    "fixed attendance must be contiguous",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
        elif task.scheduling_kind == "passive_wait" and task.active_slots not in (0, None):
            issue(
                "passive_wait_consumes_capacity",
                "passive waits cannot reserve active effort",
                task_id=task.task_id,
                constraint_ids=ids,
            )

        for resource_id in task.allowed_resource_ids or ():
            resource = resources.get(resource_id)
            if resource is None or resource.resource_kind != "human":
                issue(
                    "invalid_eligible_resource",
                    "eligible owner must be a known human resource",
                    task_id=task.task_id,
                    resource_id=resource_id,
                    constraint_ids=ids,
                )
        for resource_id in task.fixed_resource_ids:
            resource = resources.get(resource_id)
            if resource is None or resource.resource_kind != "human":
                issue(
                    "invalid_fixed_participant",
                    "fixed participant must be a known human resource",
                    task_id=task.task_id,
                    resource_id=resource_id,
                    constraint_ids=ids,
                )
            elif any(slot not in resource.available_slots for slot in task.fixed_slots):
                issue(
                    "fixed_participant_unavailable",
                    "fixed attendance falls outside participant availability",
                    task_id=task.task_id,
                    resource_id=resource_id,
                    constraint_ids=ids,
                )
        for demand in task.shared_demands:
            resource = resources.get(demand.resource_id)
            if resource is None or resource.resource_kind != "shared":
                issue(
                    "invalid_shared_resource",
                    "shared demand must reference a known shared resource",
                    task_id=task.task_id,
                    resource_id=demand.resource_id,
                    constraint_ids=ids,
                )
            elif task.scheduling_kind == "fixed_attendance" and any(
                slot not in resource.available_slots for slot in task.fixed_slots
            ):
                issue(
                    "fixed_shared_resource_unavailable",
                    "fixed attendance falls outside shared-resource availability",
                    task_id=task.task_id,
                    resource_id=demand.resource_id,
                    constraint_ids=ids,
                )

        if task.deadline is not None:
            for value in (
                task.deadline.requested_finish_slot,
                task.deadline.agreed_finish_slot,
                task.deadline.forecast_finish_slot,
                task.deadline.hard_finish_slot,
                task.deadline.max_authorized_finish_slot,
            ):
                if value is not None and value > snapshot.slot_count:
                    issue(
                        "deadline_outside_horizon",
                        "task deadline exceeds the planning horizon",
                        task_id=task.task_id,
                        constraint_ids=ids,
                    )
        if task.movement in ("locked", "authorized"):
            if task.existing_resource_id not in resources:
                issue(
                    "unknown_existing_resource",
                    "existing assignment owner is not in the snapshot",
                    task_id=task.task_id,
                    resource_id=task.existing_resource_id,
                    constraint_ids=ids,
                )
            if any(slot < 0 or slot >= snapshot.slot_count for slot in task.existing_slots):
                issue(
                    "existing_slots_outside_horizon",
                    "existing assignment falls outside the horizon",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.scheduling_kind not in ("flexible_active", "review"):
                issue(
                    "unsupported_existing_task_kind",
                    "only active or review tasks may use movement constraints",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            if task.existing_resource_id not in (task.allowed_resource_ids or ()):
                issue(
                    "existing_owner_ineligible",
                    "existing task owner is outside the validated eligibility domain",
                    task_id=task.task_id,
                    resource_id=task.existing_resource_id,
                    constraint_ids=ids,
                )
            if task.active_slots is not None and len(set(task.existing_slots)) != task.active_slots:
                issue(
                    "existing_effort_mismatch",
                    "existing task slots do not equal validated active effort",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )
            existing_resource = (
                resources.get(task.existing_resource_id)
                if task.existing_resource_id is not None
                else None
            )
            if existing_resource is not None and any(
                slot not in existing_resource.available_slots for slot in task.existing_slots
            ):
                issue(
                    "existing_owner_unavailable",
                    "existing task falls outside current owner availability",
                    task_id=task.task_id,
                    resource_id=task.existing_resource_id,
                    constraint_ids=ids,
                )
            if (
                task.release_slot is not None
                and task.window_end_slot is not None
                and any(
                    slot < task.release_slot or slot >= task.window_end_slot
                    for slot in task.existing_slots
                )
            ):
                issue(
                    "existing_slots_outside_window",
                    "existing task falls outside its validated working window",
                    task_id=task.task_id,
                    constraint_ids=ids,
                )

    for reservation in reservations:
        resource = resources.get(reservation.resource_id)
        if resource is None:
            issue(
                "unknown_reserved_resource",
                "reservation refers to an unknown resource",
                resource_id=reservation.resource_id,
                constraint_ids=(reservation.constraint_id,),
            )
            continue
        if len(reservation.slots) != len(set(reservation.slots)) or any(
            slot < 0 or slot >= snapshot.slot_count for slot in reservation.slots
        ):
            issue(
                "invalid_reservation_slots",
                "reservation slots must be unique and inside the horizon",
                resource_id=reservation.resource_id,
                constraint_ids=(reservation.constraint_id,),
            )
        if reservation.capacity_units > resource.capacity_per_slot:
            issue(
                "reservation_exceeds_capacity",
                "reservation alone exceeds resource capacity",
                resource_id=reservation.resource_id,
                constraint_ids=(reservation.constraint_id, resource.constraint_id),
            )

    for dependency in dependencies:
        if dependency.predecessor_task_id not in tasks or dependency.successor_task_id not in tasks:
            issue(
                "unknown_dependency_task",
                "dependency endpoint is not in the snapshot",
                constraint_ids=(dependency.constraint_id,),
            )
    for review in reviews:
        review_task = tasks.get(review.review_task_id)
        reviewed_task = tasks.get(review.reviewed_task_id)
        if review_task is None or reviewed_task is None:
            issue(
                "unknown_review_task",
                "review relationship refers to an unknown task",
                constraint_ids=(review.constraint_id,),
            )
        elif review_task.scheduling_kind != "review":
            issue(
                "invalid_review_kind",
                "review relationship must reference a review task",
                task_id=review.review_task_id,
                constraint_ids=(review.constraint_id, review_task.definition_constraint_id),
            )

    review_by_task: dict[UUID, list[ReviewSpec]] = defaultdict(list)
    for review in reviews:
        review_by_task[review.reviewed_task_id].append(review)
    for dependency in dependencies:
        if dependency.acceptance_required and not review_by_task[dependency.predecessor_task_id]:
            issue(
                "missing_acceptance_review",
                "acceptance-gated dependency requires a concrete review task",
                task_id=dependency.successor_task_id,
                constraint_ids=(dependency.constraint_id,),
            )

    for gate in execution_gates:
        if gate.predecessor_task_id not in tasks or gate.successor_task_id not in tasks:
            issue("unknown_execution_gate_task", "execution gate refers to an unknown task")
    for task in tasks.values():
        if task.review_policy is not None and set(task.review_policy.review_task_ids) != {
            review.review_task_id for review in reviews if review.reviewed_task_id == task.task_id
        }:
            issue(
                "review_policy_reservation_mismatch",
                "review policy must name exactly its admitted review reservations",
                task_id=task.task_id,
                constraint_ids=task.constraint_ids,
            )
    gate_edges = tuple(
        DependencySpec(
            gate.predecessor_task_id,
            gate.successor_task_id,
            gate.minimum_lag_slots,
            False,
            "execution_gate",
        )
        for gate in execution_gates
    )
    if _cycle_exists(set(tasks), (*dependencies, *gate_edges), tuple(reviews)):
        issue(
            "dependency_cycle",
            "task dependencies and reviews contain a directed cycle",
            constraint_ids=(
                *(item.constraint_id for item in dependencies),
                *(item.constraint_id for item in reviews),
            ),
        )

    boolean_variables = sum(
        len(task.allowed_resource_ids or ()) * snapshot.slot_count
        for task in tasks.values()
        if task.scheduling_kind in ("flexible_active", "review")
    )
    if boolean_variables > snapshot.policy.max_boolean_variables:
        issue("variable_limit_exceeded", "compiled model would exceed the Boolean variable limit")

    if issues:
        raise PlanningInputError(tuple(issues))
    return NormalizedPlanningModel(
        snapshot=snapshot,
        resources=resources,
        tasks=tasks,
        reservations=tuple(reservations),
        dependencies=tuple(dependencies),
        reviews=tuple(reviews),
        execution_gates=tuple(execution_gates),
        constraint_ids=tuple(constraint.constraint_id for constraint in snapshot.constraints),
    )
