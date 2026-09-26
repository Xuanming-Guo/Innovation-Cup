from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from coordination.planning.contracts import (
    DeadlinePayload,
    DependencyPayload,
    EffortPayload,
    EligibilityPayload,
    FixedAttendancePayload,
    MovementPayload,
    PlanningPolicy,
    PlanningSnapshot,
    PriorityPayload,
    ReservationPayload,
    ResourceCapacityPayload,
    ReviewPayload,
    ScheduleBlock,
    SegmentationPayload,
    SharedResourceDemand,
    SharedResourcePayload,
    TaskDefinitionPayload,
    ValidatedConstraint,
    WorkingWindowPayload,
)
from coordination.planning.engine import PlanningEngine, classify_unknown_termination
from coordination.planning.normalizer import normalize_snapshot
from coordination.planning.validator import validate_schedule

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
REQUEST_ID = UUID("22222222-2222-4222-8222-222222222222")
CANDIDATE_ID = UUID("33333333-3333-4333-8333-333333333333")
SNAPSHOT_ID = UUID("44444444-4444-4444-8444-444444444444")
ALICE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
BOB_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ROOM_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
BUILD_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
REVIEW_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SECOND_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
HORIZON_START = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


def validated(
    constraint_id: str,
    payload: object,
    *,
    strength: str = "hard",
    negotiability: str = "locked",
) -> ValidatedConstraint:
    return ValidatedConstraint.model_validate(
        {
            "constraint_id": constraint_id,
            "company_id": str(COMPANY_ID),
            "strength": strength,
            "payload": payload,
            "source_version_ids": [],
            "authority_refs": ["fixture:manager-approved"],
            "negotiability": negotiability,
        }
    )


def resource(
    resource_id: UUID,
    *,
    slots: int,
    kind: str = "human",
    capacity: int = 1,
) -> ValidatedConstraint:
    return validated(
        f"resource.{resource_id.hex}",
        ResourceCapacityPayload.model_validate(
            {
                "family": "resource_capacity",
                "resource_id": resource_id,
                "resource_kind": kind,
                "timezone": "UTC",
                "available_slots": list(range(slots)),
                "capacity_per_slot": capacity,
                "daily_budgets": [{"day_index": 0, "max_active_slots": slots * capacity}],
                "capability_keys": ["general", "review"],
                "permission_keys": ["project"],
            }
        ),
    )


def add_active_task(
    constraints: list[ValidatedConstraint],
    *,
    task_id: UUID,
    key: str,
    eligible: tuple[UUID, ...],
    effort: int,
    release: int,
    end: int,
    priority: int = 5,
    kind: str = "flexible_active",
    hard_deadline: int | None = None,
    movement: Literal["new", "locked", "authorized"] = "new",
    existing_resource_id: UUID | None = None,
    existing_slots: tuple[int, ...] = (),
    shared_resource_id: UUID | None = None,
) -> None:
    constraints.extend(
        (
            validated(
                f"{key}.definition",
                TaskDefinitionPayload.model_validate(
                    {
                        "family": "task_definition",
                        "task_id": task_id,
                        "task_key": key,
                        "title": key.replace("_", " ").title(),
                        "scheduling_kind": kind,
                    }
                ),
            ),
            validated(
                f"{key}.effort",
                EffortPayload(
                    family="effort",
                    task_id=task_id,
                    active_slots=effort,
                    elapsed_slots=effort,
                ),
            ),
            validated(
                f"{key}.eligibility",
                EligibilityPayload(
                    family="eligibility",
                    task_id=task_id,
                    allowed_resource_ids=eligible,
                ),
            ),
            validated(
                f"{key}.window",
                WorkingWindowPayload(
                    family="working_window",
                    task_id=task_id,
                    release_slot=release,
                    end_slot=end,
                ),
            ),
            validated(
                f"{key}.segments",
                SegmentationPayload(
                    family="segmentation",
                    task_id=task_id,
                    split_allowed=True,
                    minimum_segment_slots=min(2, effort),
                    max_segments_per_day=4,
                ),
            ),
            validated(
                f"{key}.movement",
                MovementPayload(
                    family="movement",
                    task_id=task_id,
                    movement=movement,
                    existing_resource_id=existing_resource_id,
                    existing_slots=existing_slots,
                ),
                negotiability="authorized" if movement == "authorized" else "locked",
            ),
            validated(
                f"{key}.priority",
                PriorityPayload(family="priority", task_id=task_id, tier=priority),
                strength="preferred",
                negotiability="preferred",
            ),
        )
    )
    if hard_deadline is not None:
        constraints.append(
            validated(
                f"{key}.deadline",
                DeadlinePayload(
                    family="deadline",
                    task_id=task_id,
                    requested_finish_slot=hard_deadline,
                    agreed_finish_slot=hard_deadline,
                    forecast_finish_slot=None,
                    hard_finish_slot=hard_deadline,
                    max_authorized_finish_slot=None,
                ),
            )
        )
    if shared_resource_id is not None:
        constraints.append(
            validated(
                f"{key}.shared",
                SharedResourcePayload(
                    family="shared_resource",
                    task_id=task_id,
                    demands=(
                        SharedResourceDemand(
                            resource_id=shared_resource_id,
                            capacity_units=1,
                        ),
                    ),
                ),
            )
        )


def add_fixed_task(
    constraints: list[ValidatedConstraint],
    *,
    task_id: UUID,
    key: str,
    participants: tuple[UUID, ...],
    occupied_slots: tuple[int, ...],
) -> None:
    constraints.extend(
        (
            validated(
                f"{key}.definition",
                TaskDefinitionPayload(
                    family="task_definition",
                    task_id=task_id,
                    task_key=key,
                    title=key.replace("_", " ").title(),
                    scheduling_kind="fixed_attendance",
                ),
            ),
            validated(
                f"{key}.effort",
                EffortPayload(
                    family="effort",
                    task_id=task_id,
                    active_slots=len(occupied_slots),
                    elapsed_slots=len(occupied_slots),
                ),
            ),
            validated(
                f"{key}.window",
                WorkingWindowPayload(
                    family="working_window",
                    task_id=task_id,
                    release_slot=occupied_slots[0],
                    end_slot=occupied_slots[-1] + 1,
                ),
            ),
            validated(
                f"{key}.fixed",
                FixedAttendancePayload(
                    family="fixed_attendance",
                    task_id=task_id,
                    participant_resource_ids=participants,
                    slots=occupied_slots,
                ),
            ),
            validated(
                f"{key}.movement",
                MovementPayload(
                    family="movement",
                    task_id=task_id,
                    movement="new",
                    existing_resource_id=None,
                    existing_slots=(),
                ),
            ),
        )
    )


def snapshot(
    constraints: list[ValidatedConstraint],
    *,
    slots: int,
    allow_repair: bool = True,
    max_boolean_variables: int = 2_000_000,
) -> PlanningSnapshot:
    return PlanningSnapshot.freeze(
        snapshot_id=SNAPSHOT_ID,
        company_id=COMPANY_ID,
        request_id=REQUEST_ID,
        candidate_contract_id=CANDIDATE_ID,
        base_company_revision=7,
        horizon_start=HORIZON_START,
        horizon_end=HORIZON_START + timedelta(minutes=15 * slots),
        slot_minutes=15,
        source_manifest_digest="ab" * 32,
        permission_revision="permissions:7",
        profile_revision="profiles:3",
        estimate_revision="estimates:2",
        compiler_version="coordination-z3-compiler.v1",
        policy=PlanningPolicy(
            policy_version="priority-policy:1",
            timeout_ms=5_000,
            resource_limit=10_000_000,
            allow_authorized_repair=allow_repair,
            max_repair_attempts=1 if allow_repair else 0,
            max_slots=slots,
            max_boolean_variables=max_boolean_variables,
        ),
        constraints=tuple(constraints),
        frozen_at=HORIZON_START - timedelta(minutes=5),
    )


def test_same_snapshot_is_reproducible_and_enforces_dependency_review_and_deadline() -> None:
    constraints = [resource(ALICE_ID, slots=16), resource(BOB_ID, slots=16)]
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="build",
        eligible=(ALICE_ID,),
        effort=4,
        release=0,
        end=12,
        priority=0,
        hard_deadline=8,
    )
    add_active_task(
        constraints,
        task_id=REVIEW_ID,
        key="review",
        eligible=(ALICE_ID, BOB_ID),
        effort=2,
        release=0,
        end=16,
        priority=0,
        kind="review",
        hard_deadline=12,
    )
    add_active_task(
        constraints,
        task_id=SECOND_ID,
        key="publish",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=16,
        priority=0,
        hard_deadline=16,
    )
    constraints.extend(
        (
            validated(
                "build.before_review",
                DependencyPayload(
                    family="dependency_lag",
                    predecessor_task_id=BUILD_ID,
                    successor_task_id=REVIEW_ID,
                    minimum_lag_slots=1,
                    acceptance_required=False,
                ),
            ),
            validated(
                "build.accepted_before_publish",
                DependencyPayload(
                    family="dependency_lag",
                    predecessor_task_id=BUILD_ID,
                    successor_task_id=SECOND_ID,
                    minimum_lag_slots=0,
                    acceptance_required=True,
                ),
            ),
            validated(
                "build.independent_review",
                ReviewPayload(
                    family="acceptance_review",
                    review_task_id=REVIEW_ID,
                    reviewed_task_id=BUILD_ID,
                    require_separate_resource=True,
                ),
            ),
        )
    )
    frozen = snapshot(constraints, slots=16)

    first = PlanningEngine().plan(frozen)
    second = PlanningEngine().plan(frozen)

    assert first.classification in ("OPTIMAL_WITHIN_MODEL", "FEASIBLE")
    assert second.classification == first.classification
    first_attempt = first.attempts[first.selected_attempt or 0]
    second_attempt = second.attempts[second.selected_attempt or 0]
    assert first_attempt.placements == second_attempt.placements
    assert first_attempt.blocks == second_attempt.blocks
    assert first_attempt.validation is not None and first_attempt.validation.valid
    assert second_attempt.validation is not None
    assert first_attempt.validation.schedule_digest == second_attempt.validation.schedule_digest
    placements = {placement.task_id: placement for placement in first_attempt.placements}
    assert placements[BUILD_ID].owner_resource_id == ALICE_ID
    assert placements[REVIEW_ID].owner_resource_id == BOB_ID
    assert placements[REVIEW_ID].start_slot >= placements[BUILD_ID].end_slot + 1
    assert placements[SECOND_ID].start_slot >= placements[REVIEW_ID].end_slot
    assert placements[BUILD_ID].end_slot <= 8
    assert placements[REVIEW_ID].end_slot <= 12
    assert placements[SECOND_ID].end_slot <= 16


def test_fixed_attendance_and_existing_reservation_prevent_double_booking() -> None:
    constraints = [resource(ALICE_ID, slots=8)]
    add_fixed_task(
        constraints,
        task_id=SECOND_ID,
        key="fixed_meeting",
        participants=(ALICE_ID,),
        occupied_slots=(0, 1),
    )
    constraints.append(
        validated(
            "alice.external_reservation",
            ReservationPayload(
                family="reservation",
                resource_id=ALICE_ID,
                reservation_ref="calendar:busy",
                slots=(2,),
                capacity_units=1,
                consumes_daily_budget=True,
            ),
        )
    )
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="focused_work",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=8,
    )

    plan = PlanningEngine().plan(snapshot(constraints, slots=8))
    attempt = plan.attempts[plan.selected_attempt or 0]
    owner_slots = {
        slot
        for block in attempt.blocks
        if block.task_id == BUILD_ID and block.role == "owner"
        for slot in range(block.start_slot, block.end_slot)
    }
    assert owner_slots.isdisjoint({0, 1, 2})
    assert attempt.validation is not None and attempt.validation.valid


def test_shared_capacity_serializes_independent_work_on_different_people() -> None:
    constraints = [
        resource(ALICE_ID, slots=8),
        resource(BOB_ID, slots=8),
        resource(ROOM_ID, slots=8, kind="shared"),
    ]
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="room_work_a",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=6,
        shared_resource_id=ROOM_ID,
    )
    add_active_task(
        constraints,
        task_id=SECOND_ID,
        key="room_work_b",
        eligible=(BOB_ID,),
        effort=2,
        release=0,
        end=6,
        shared_resource_id=ROOM_ID,
    )

    plan = PlanningEngine().plan(snapshot(constraints, slots=8))
    attempt = plan.attempts[plan.selected_attempt or 0]
    room_usage: dict[int, int] = {}
    for block in attempt.blocks:
        if block.resource_id == ROOM_ID:
            for slot in range(block.start_slot, block.end_slot):
                room_usage[slot] = room_usage.get(slot, 0) + block.capacity_units
    assert room_usage and max(room_usage.values()) == 1
    assert attempt.validation is not None and attempt.validation.valid


def test_pinned_insertion_failure_can_use_one_authorized_repair_without_weakening() -> None:
    constraints = [resource(ALICE_ID, slots=6)]
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="existing_work",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=6,
        priority=5,
        movement="authorized",
        existing_resource_id=ALICE_ID,
        existing_slots=(0, 1),
    )
    add_active_task(
        constraints,
        task_id=SECOND_ID,
        key="urgent_work",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=2,
        priority=0,
        hard_deadline=2,
    )

    plan = PlanningEngine().plan(snapshot(constraints, slots=6))

    assert len(plan.attempts) == 2
    assert plan.attempts[0].classification == "INFEASIBLE_WITHIN_SCOPE"
    assert plan.attempts[0].scope == "pinned_insertion"
    assert plan.attempts[1].classification in ("OPTIMAL_WITHIN_MODEL", "FEASIBLE")
    assert plan.attempts[1].scope == "authorized_repair"
    assert plan.selected_attempt == 1
    assert plan.attempts[0].model is not None
    assert plan.attempts[1].model is not None
    assert plan.attempts[0].model.constraint_ids == plan.attempts[1].model.constraint_ids
    placements = {placement.task_id: placement for placement in plan.attempts[1].placements}
    assert placements[SECOND_ID].end_slot <= 2
    assert placements[BUILD_ID].start_slot >= 2
    assert plan.attempts[1].validation is not None and plan.attempts[1].validation.valid


def test_unsat_and_invalid_input_are_distinct_and_diagnosed() -> None:
    impossible = [resource(ALICE_ID, slots=4)]
    add_active_task(
        impossible,
        task_id=BUILD_ID,
        key="impossible_deadline",
        eligible=(ALICE_ID,),
        effort=3,
        release=0,
        end=4,
        hard_deadline=2,
    )
    unsat = PlanningEngine().plan(snapshot(impossible, slots=4, allow_repair=False))
    assert unsat.classification == "INFEASIBLE_WITHIN_SCOPE"
    assert unsat.attempts[0].raw_status == "unsat"
    assert unsat.attempts[0].termination == "completed"
    assert unsat.attempts[0].diagnostic_constraint_ids

    malformed = [resource(ALICE_ID, slots=4)]
    malformed.extend(
        (
            validated(
                "bad.definition",
                TaskDefinitionPayload(
                    family="task_definition",
                    task_id=BUILD_ID,
                    task_key="bad",
                    title="Bad",
                    scheduling_kind="flexible_active",
                ),
            ),
            validated(
                "bad.window",
                WorkingWindowPayload(
                    family="working_window", task_id=BUILD_ID, release_slot=0, end_slot=4
                ),
            ),
            validated(
                "bad.movement",
                MovementPayload(
                    family="movement",
                    task_id=BUILD_ID,
                    movement="new",
                    existing_resource_id=None,
                    existing_slots=(),
                ),
            ),
        )
    )
    invalid = PlanningEngine().plan(snapshot(malformed, slots=4, allow_repair=False))
    assert invalid.classification == "INVALID_INPUT"
    assert invalid.attempts[0].raw_status == "invalid"
    assert invalid.attempts[0].termination == "invalid"
    assert invalid.attempts[0].validation is not None
    assert {issue.code for issue in invalid.attempts[0].validation.issues} >= {
        "missing_effort",
        "empty_eligibility",
    }


def test_independent_validator_rejects_corrupted_solver_output() -> None:
    constraints = [resource(ALICE_ID, slots=6)]
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="validated_work",
        eligible=(ALICE_ID,),
        effort=2,
        release=0,
        end=6,
    )
    frozen = snapshot(constraints, slots=6)
    plan = PlanningEngine().plan(frozen)
    attempt = plan.attempts[plan.selected_attempt or 0]
    assert attempt.validation is not None and attempt.validation.valid
    original = next(block for block in attempt.blocks if block.role == "owner")
    corrupted = (
        ScheduleBlock(
            task_id=original.task_id,
            resource_id=original.resource_id,
            start_slot=original.start_slot,
            end_slot=original.end_slot - 1,
            capacity_units=original.capacity_units,
            role=original.role,
        ),
    )

    report = validate_schedule(
        normalize_snapshot(frozen),
        scope=attempt.scope,
        placements=attempt.placements,
        blocks=corrupted,
    )

    assert report.valid is False
    assert {item.code for item in report.issues} >= {"effort_mismatch", "placement_block_mismatch"}


def test_unknown_termination_preserves_timeout_and_resource_limit_causes() -> None:
    assert classify_unknown_termination("timeout") == "timeout"
    assert classify_unknown_termination("canceled") == "timeout"
    assert classify_unknown_termination("max. resource limit exceeded") == "resource_limit"
    assert classify_unknown_termination("incomplete theory") == "unknown"


def test_boolean_variable_budget_rejects_oversized_model_before_z3() -> None:
    resource_ids = tuple(UUID(int=10_000 + index) for index in range(20))
    constraints = [resource(resource_id, slots=60) for resource_id in resource_ids]
    add_active_task(
        constraints,
        task_id=BUILD_ID,
        key="bounded_work",
        eligible=resource_ids,
        effort=2,
        release=0,
        end=60,
    )

    plan = PlanningEngine().plan(
        snapshot(
            constraints,
            slots=60,
            allow_repair=False,
            max_boolean_variables=1_000,
        )
    )

    assert plan.classification == "INVALID_INPUT"
    assert plan.attempts[0].model is None
    assert plan.attempts[0].validation is not None
    assert "variable_limit_exceeded" in {issue.code for issue in plan.attempts[0].validation.issues}
