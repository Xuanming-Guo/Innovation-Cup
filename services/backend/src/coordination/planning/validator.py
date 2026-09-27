from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from coordination.planning.contracts import (
    PlanningScope,
    ScheduleBlock,
    TaskPlacement,
    ValidationIssue,
    ValidationReport,
    canonical_digest,
)
from coordination.planning.normalizer import NormalizedPlanningModel, TaskSpec

VALIDATOR_VERSION = "coordination-schedule-validator.v1"


def _expanded_slots(blocks: list[ScheduleBlock]) -> list[int]:
    return [slot for block in blocks for slot in range(block.start_slot, block.end_slot)]


def _segment_lengths(
    slots: list[int], *, slots_per_day: int, local_days: Mapping[int, object] | None = None
) -> list[tuple[int, int]]:
    if not slots:
        return []
    values = sorted(set(slots))
    segments: list[tuple[int, int]] = []
    start = values[0]
    previous = values[0]
    for slot in values[1:]:
        same_day = (
            (local_days[slot] == local_days[previous])
            if local_days is not None
            else (slot // slots_per_day == previous // slots_per_day)
        )
        if slot != previous + 1 or not same_day:
            segments.append((start, previous - start + 1))
            start = slot
        previous = slot
    segments.append((start, previous - start + 1))
    return segments


def validate_schedule(
    normalized: NormalizedPlanningModel,
    *,
    scope: PlanningScope,
    placements: tuple[TaskPlacement, ...],
    blocks: tuple[ScheduleBlock, ...],
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    placement_map: dict[UUID, TaskPlacement] = {}
    task_blocks: dict[UUID, list[ScheduleBlock]] = defaultdict(list)

    def issue(
        code: str,
        message: str,
        *,
        task: TaskSpec | None = None,
        task_id: UUID | None = None,
        resource_id: UUID | None = None,
        constraint_ids: tuple[str, ...] = (),
    ) -> None:
        issues.append(
            ValidationIssue(
                code=code,
                message=message,
                task_id=task.task_id if task is not None else task_id,
                resource_id=resource_id,
                constraint_ids=constraint_ids or (task.constraint_ids if task is not None else ()),
            )
        )

    for submitted_placement in placements:
        if submitted_placement.task_id in placement_map:
            issue(
                "duplicate_placement",
                "schedule contains duplicate task placements",
                task_id=submitted_placement.task_id,
            )
        placement_map[submitted_placement.task_id] = submitted_placement
        if submitted_placement.end_slot <= submitted_placement.start_slot:
            issue(
                "invalid_placement_interval",
                "task placement has a non-positive interval",
                task_id=submitted_placement.task_id,
            )

    for block in blocks:
        task = normalized.tasks.get(block.task_id)
        resource = normalized.resources.get(block.resource_id)
        if task is None:
            issue(
                "unknown_block_task",
                "schedule block refers to an unknown task",
                task_id=block.task_id,
                resource_id=block.resource_id,
            )
            continue
        if resource is None:
            issue(
                "unknown_block_resource",
                "schedule block refers to an unknown resource",
                task=task,
                resource_id=block.resource_id,
            )
            continue
        if block.end_slot <= block.start_slot or block.end_slot > normalized.snapshot.slot_count:
            issue(
                "invalid_block_interval",
                "schedule block is outside the finite horizon",
                task=task,
                resource_id=block.resource_id,
            )
            continue
        if any(
            slot not in resource.available_slots for slot in range(block.start_slot, block.end_slot)
        ):
            issue(
                "resource_unavailable",
                "schedule block falls outside current resource availability",
                task=task,
                resource_id=block.resource_id,
                constraint_ids=(resource.constraint_id, *task.constraint_ids),
            )
        task_blocks[block.task_id].append(block)

    for task in normalized.tasks.values():
        placement = placement_map.get(task.task_id)
        if placement is None:
            issue("missing_placement", "task has no schedule placement", task=task)
            continue
        if task.release_slot is not None and placement.start_slot < task.release_slot:
            issue("before_release", "task begins before its working window", task=task)
        if task.window_end_slot is not None and placement.end_slot > task.window_end_slot:
            issue("after_window", "task ends after its working window", task=task)
        if task.deadline is not None:
            if (
                task.deadline.hard_finish_slot is not None
                and placement.end_slot > task.deadline.hard_finish_slot
            ):
                issue(
                    "hard_deadline_missed",
                    "task finishes after a hard deadline",
                    task=task,
                    constraint_ids=(task.deadline_constraint_id or task.definition_constraint_id,),
                )
            if (
                task.deadline.max_authorized_finish_slot is not None
                and placement.end_slot > task.deadline.max_authorized_finish_slot
            ):
                issue(
                    "deadline_authority_exceeded",
                    "task exceeds the authorized deadline envelope",
                    task=task,
                    constraint_ids=(task.deadline_constraint_id or task.definition_constraint_id,),
                )

        owner_blocks = [block for block in task_blocks[task.task_id] if block.role == "owner"]
        participant_blocks = [
            block for block in task_blocks[task.task_id] if block.role == "participant"
        ]
        shared_blocks = [block for block in task_blocks[task.task_id] if block.role == "shared"]
        if task.scheduling_kind in ("flexible_active", "review"):
            if placement.owner_resource_id not in (task.allowed_resource_ids or ()):
                issue(
                    "ineligible_owner",
                    "task owner is outside the validated eligibility domain",
                    task=task,
                    resource_id=placement.owner_resource_id,
                    constraint_ids=(
                        task.eligibility_constraint_id or task.definition_constraint_id,
                    ),
                )
            expected_participants = set(task.participant_resource_ids) - {
                placement.owner_resource_id
            }
            if {block.resource_id for block in participant_blocks} != expected_participants:
                issue(
                    "unexpected_participant_block",
                    "active task participants do not match the admitted participant set",
                    task=task,
                )
            if any(
                block.resource_id != placement.owner_resource_id or block.capacity_units != 1
                for block in owner_blocks
            ):
                issue(
                    "owner_block_mismatch",
                    "owner blocks do not match the selected owner",
                    task=task,
                    resource_id=placement.owner_resource_id,
                )
            slots = _expanded_slots(owner_blocks)
            for participant_id in expected_participants:
                participant_reservations = [
                    block for block in participant_blocks if block.resource_id == participant_id
                ]
                participant_slots = _expanded_slots(participant_reservations)
                if sorted(participant_slots) != sorted(slots) or any(
                    block.capacity_units != 1 for block in participant_reservations
                ):
                    issue(
                        "participant_effort_mismatch",
                        "every active participant must reserve the owner's full active interval",
                        task=task,
                        resource_id=participant_id,
                        constraint_ids=(
                            task.participants_constraint_id or task.definition_constraint_id,
                        ),
                    )
            if len(slots) != len(set(slots)):
                issue(
                    "duplicate_task_capacity",
                    "task reserves its owner more than once in a slot",
                    task=task,
                    resource_id=placement.owner_resource_id,
                )
            if len(set(slots)) != task.active_slots:
                issue(
                    "effort_mismatch",
                    "reserved active effort does not equal the validated estimate",
                    task=task,
                    constraint_ids=(task.effort_constraint_id or task.definition_constraint_id,),
                )
            if slots and (
                placement.start_slot != min(slots) or placement.end_slot != max(slots) + 1
            ):
                issue(
                    "placement_block_mismatch",
                    "task placement does not match its concrete active blocks",
                    task=task,
                )
            slots_per_day = max(1, 1_440 // normalized.snapshot.slot_minutes)
            owner = (
                normalized.resources.get(placement.owner_resource_id)
                if placement.owner_resource_id is not None
                else None
            )
            zone = ZoneInfo(owner.timezone if owner is not None else "UTC")
            local_days = {
                slot: (
                    normalized.snapshot.horizon_start.astimezone(UTC)
                    + timedelta(minutes=slot * normalized.snapshot.slot_minutes)
                )
                .astimezone(zone)
                .date()
                for slot in set(slots)
            }
            segments = _segment_lengths(slots, slots_per_day=slots_per_day, local_days=local_days)
            if not task.split_allowed and len(segments) > 1:
                issue(
                    "unauthorized_split",
                    "task was split without authorization",
                    task=task,
                    constraint_ids=(
                        task.segmentation_constraint_id or task.definition_constraint_id,
                    ),
                )
            minimum = min(task.minimum_segment_slots or 1, task.active_slots or 1)
            if any(length < minimum for _start, length in segments):
                issue(
                    "segment_too_short",
                    "task contains a segment below the configured minimum",
                    task=task,
                    constraint_ids=(
                        task.segmentation_constraint_id or task.definition_constraint_id,
                    ),
                )
            by_day: dict[object, int] = defaultdict(int)
            for start, _length in segments:
                by_day[local_days[start]] += 1
            if any(count > (task.max_segments_per_day or 1) for count in by_day.values()):
                issue(
                    "excessive_fragmentation",
                    "task exceeds the daily segment limit",
                    task=task,
                    constraint_ids=(
                        task.segmentation_constraint_id or task.definition_constraint_id,
                    ),
                )
        elif task.scheduling_kind == "fixed_attendance":
            if placement.owner_resource_id is not None or owner_blocks:
                issue(
                    "fixed_task_has_owner",
                    "fixed attendance uses participants rather than an interchangeable owner",
                    task=task,
                )
            if (
                placement.start_slot != task.fixed_slots[0]
                or placement.end_slot != task.fixed_slots[-1] + 1
            ):
                issue(
                    "fixed_placement_mismatch",
                    "fixed attendance placement was moved",
                    task=task,
                    constraint_ids=(task.fixed_constraint_id or task.definition_constraint_id,),
                )
            for resource_id in task.fixed_resource_ids:
                resource_blocks = [
                    block for block in participant_blocks if block.resource_id == resource_id
                ]
                actual = set(_expanded_slots(resource_blocks))
                if actual != set(task.fixed_slots):
                    issue(
                        "fixed_participant_mismatch",
                        "fixed participant reservations were changed",
                        task=task,
                        resource_id=resource_id,
                        constraint_ids=(task.fixed_constraint_id or task.definition_constraint_id,),
                    )
                if any(block.capacity_units != 1 for block in resource_blocks):
                    issue(
                        "fixed_participant_capacity_mismatch",
                        "fixed participant reservations must consume one capacity unit",
                        task=task,
                        resource_id=resource_id,
                        constraint_ids=(task.fixed_constraint_id or task.definition_constraint_id,),
                    )
            for resource_id in {block.resource_id for block in participant_blocks} - set(
                task.fixed_resource_ids
            ):
                issue(
                    "unexpected_fixed_participant",
                    "fixed attendance contains an undeclared participant",
                    task=task,
                    resource_id=resource_id,
                    constraint_ids=(task.fixed_constraint_id or task.definition_constraint_id,),
                )
        else:
            if (
                placement.owner_resource_id is not None
                or owner_blocks
                or participant_blocks
                or shared_blocks
            ):
                issue(
                    "passive_wait_reserved_capacity",
                    "passive wait cannot reserve execution capacity",
                    task=task,
                )
            if placement.end_slot - placement.start_slot != task.elapsed_slots:
                issue(
                    "passive_duration_mismatch",
                    "passive wait duration changed",
                    task=task,
                    constraint_ids=(task.effort_constraint_id or task.definition_constraint_id,),
                )

        occupied_slots = set(_expanded_slots(owner_blocks or participant_blocks))
        for demand in task.shared_demands:
            actual_blocks = [
                block for block in shared_blocks if block.resource_id == demand.resource_id
            ]
            actual_slots = set(_expanded_slots(actual_blocks))
            if actual_slots != occupied_slots or any(
                block.capacity_units != demand.capacity_units for block in actual_blocks
            ):
                issue(
                    "shared_resource_mismatch",
                    "shared-resource reservations do not match task activity",
                    task=task,
                    resource_id=demand.resource_id,
                    constraint_ids=(task.shared_constraint_id or task.definition_constraint_id,),
                )
        unexpected_shared = {block.resource_id for block in shared_blocks} - {
            demand.resource_id for demand in task.shared_demands
        }
        for resource_id in unexpected_shared:
            issue(
                "unexpected_shared_resource",
                "task reserves an undeclared shared resource",
                task=task,
                resource_id=resource_id,
            )

        should_pin = task.movement == "locked" or (
            scope == "pinned_insertion" and task.movement == "authorized"
        )
        if should_pin:
            actual_slots = set(_expanded_slots(owner_blocks))
            if placement.owner_resource_id != task.existing_resource_id or actual_slots != set(
                task.existing_slots
            ):
                issue(
                    "protected_commitment_moved",
                    "protected existing work changed in this solve scope",
                    task=task,
                    constraint_ids=(task.movement_constraint_id or task.definition_constraint_id,),
                )

    for dependency in normalized.dependencies:
        predecessor = placement_map.get(dependency.predecessor_task_id)
        successor = placement_map.get(dependency.successor_task_id)
        predecessor_placements = [predecessor] if predecessor is not None else []
        if dependency.acceptance_required:
            predecessor_placements = [
                placement_map[review.review_task_id]
                for review in normalized.reviews
                if review.reviewed_task_id == dependency.predecessor_task_id
                and review.review_task_id in placement_map
            ]
        if successor is not None and any(
            successor.start_slot < item.end_slot + dependency.minimum_lag_slots
            for item in predecessor_placements
        ):
            issue(
                "dependency_violation",
                "successor begins before its predecessor gate and lag complete",
                task_id=dependency.successor_task_id,
                constraint_ids=(dependency.constraint_id,),
            )

    for review in normalized.reviews:
        reviewer = placement_map.get(review.review_task_id)
        reviewed = placement_map.get(review.reviewed_task_id)
        if reviewer is None or reviewed is None:
            continue
        if reviewer.start_slot < reviewed.end_slot:
            issue(
                "review_order_violation",
                "review begins before reviewed work completes",
                task_id=review.review_task_id,
                constraint_ids=(review.constraint_id,),
            )
        if review.require_separate_resource and reviewer.owner_resource_id is not None:
            reviewed_resources = {
                block.resource_id
                for block in task_blocks[review.reviewed_task_id]
                if block.role in ("owner", "participant")
            }
            if reviewer.owner_resource_id in reviewed_resources:
                issue(
                    "review_separation_violation",
                    "reviewer is not independent from the work owner",
                    task_id=review.review_task_id,
                    resource_id=reviewer.owner_resource_id,
                    constraint_ids=(review.constraint_id,),
                )

    for gate in normalized.execution_gates:
        predecessor = placement_map.get(gate.predecessor_task_id)
        successor = placement_map.get(gate.successor_task_id)
        if (
            predecessor is None
            or successor is None
            or successor.start_slot < predecessor.end_slot + gate.minimum_lag_slots
        ):
            issue(
                "execution_gate_order",
                "successor reservation precedes its required decision/artifact gate",
                task_id=gate.successor_task_id,
            )

    usage: dict[tuple[UUID, int], int] = defaultdict(int)
    budget_usage: dict[tuple[UUID, int], int] = defaultdict(int)
    for block in blocks:
        if block.resource_id not in normalized.resources:
            continue
        for slot in range(block.start_slot, block.end_slot):
            usage[(block.resource_id, slot)] += block.capacity_units
            budget_usage[(block.resource_id, slot)] += block.capacity_units
    for reservation in normalized.reservations:
        for slot in reservation.slots:
            usage[(reservation.resource_id, slot)] += reservation.capacity_units
            if reservation.consumes_daily_budget:
                budget_usage[(reservation.resource_id, slot)] += reservation.capacity_units
    for resource in normalized.resources.values():
        for slot in range(normalized.snapshot.slot_count):
            if usage[(resource.resource_id, slot)] > resource.capacity_per_slot:
                issue(
                    "capacity_exceeded",
                    "resource capacity is exceeded in a concrete slot",
                    resource_id=resource.resource_id,
                    constraint_ids=(resource.constraint_id,),
                )
        zone = ZoneInfo(resource.timezone)
        first_day = normalized.snapshot.horizon_start.astimezone(zone).date()
        for day_index, budget in resource.daily_budgets.items():
            consumed = sum(
                units
                for (resource_id, slot), units in budget_usage.items()
                if resource_id == resource.resource_id
                and (
                    (
                        normalized.snapshot.horizon_start.astimezone(UTC)
                        + timedelta(minutes=slot * normalized.snapshot.slot_minutes)
                    )
                    .astimezone(zone)
                    .date()
                    - first_day
                ).days
                == day_index
            )
            if consumed > budget:
                issue(
                    "daily_budget_exceeded",
                    "resource exceeds its validated daily active budget",
                    resource_id=resource.resource_id,
                    constraint_ids=(resource.constraint_id,),
                )

    missing_task_ids = set(normalized.tasks) - set(placement_map)
    extra_task_ids = set(placement_map) - set(normalized.tasks)
    if missing_task_ids:
        issue("missing_tasks", "schedule omits validated tasks")
    if extra_task_ids:
        issue("extra_tasks", "schedule contains tasks outside the snapshot")

    schedule_payload = {
        "snapshot_digest": normalized.snapshot.snapshot_digest,
        "scope": scope,
        "placements": [
            placement.model_dump(mode="json")
            for placement in sorted(placements, key=lambda item: str(item.task_id))
        ],
        "blocks": [
            block.model_dump(mode="json")
            for block in sorted(
                blocks,
                key=lambda item: (
                    str(item.task_id),
                    str(item.resource_id),
                    item.start_slot,
                    item.role,
                ),
            )
        ],
    }
    return ValidationReport(
        validator_version=VALIDATOR_VERSION,
        valid=not issues,
        schedule_digest=canonical_digest(schedule_payload),
        issues=tuple(issues),
    )
