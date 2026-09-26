from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

import z3  # type: ignore[import-untyped]

from coordination.planning.contracts import (
    CompiledModel,
    ObjectiveValue,
    PlanningScope,
    ScheduleBlock,
    TaskPlacement,
    canonical_digest,
)
from coordination.planning.normalizer import NormalizedPlanningModel, TaskSpec

COMPILER_VERSION = "coordination-z3-compiler.v1"


@dataclass(frozen=True, slots=True)
class ObjectiveExpression:
    name: str
    expression: z3.ArithRef
    handle: z3.OptimizeObjective


@dataclass(slots=True)
class CompiledZ3Problem:
    normalized: NormalizedPlanningModel
    metadata: CompiledModel
    optimizer: z3.Optimize
    assignments: dict[tuple[UUID, UUID], z3.BoolRef]
    occupancy: dict[tuple[UUID, UUID, int], z3.BoolRef]
    starts: dict[UUID, z3.IntNumRef | z3.ArithRef]
    ends: dict[UUID, z3.IntNumRef | z3.ArithRef]
    segment_starts: dict[tuple[UUID, UUID, int], z3.BoolRef]
    hard_assertions: dict[str, list[z3.BoolRef]]
    objectives: list[ObjectiveExpression]


def _symbol(prefix: str, *values: object) -> str:
    return "__".join((prefix, *(str(value).replace("-", "") for value in values)))


def _sum(expressions: Iterable[z3.ArithRef]) -> z3.ArithRef:
    values = list(expressions)
    return z3.Sum(values) if values else z3.IntVal(0)


def _bool_sum(expressions: Iterable[z3.BoolRef]) -> z3.ArithRef:
    return _sum(z3.If(expression, 1, 0) for expression in expressions)


def _contiguous_blocks(slots: list[int]) -> list[tuple[int, int]]:
    if not slots:
        return []
    blocks: list[tuple[int, int]] = []
    start = slots[0]
    previous = slots[0]
    for slot in slots[1:]:
        if slot != previous + 1:
            blocks.append((start, previous + 1))
            start = slot
        previous = slot
    blocks.append((start, previous + 1))
    return blocks


def compile_snapshot(
    normalized: NormalizedPlanningModel,
    *,
    scope: PlanningScope,
) -> CompiledZ3Problem:
    snapshot = normalized.snapshot
    optimizer = z3.Optimize()
    optimizer.set(
        priority="lex",
        timeout=snapshot.policy.timeout_ms,
        rlimit=snapshot.policy.resource_limit,
    )
    assignments: dict[tuple[UUID, UUID], z3.BoolRef] = {}
    occupancy: dict[tuple[UUID, UUID, int], z3.BoolRef] = {}
    starts: dict[UUID, z3.ArithRef] = {}
    ends: dict[UUID, z3.ArithRef] = {}
    segment_starts: dict[tuple[UUID, UUID, int], z3.BoolRef] = {}
    hard_assertions: dict[str, list[z3.BoolRef]] = defaultdict(list)

    def add(expression: z3.BoolRef, constraint_id: str) -> None:
        optimizer.add(expression)
        hard_assertions[constraint_id].append(expression)

    task_order = sorted(
        normalized.tasks.values(), key=lambda item: (item.task_key, str(item.task_id))
    )
    for task in task_order:
        start = z3.Int(_symbol("start", task.task_id))
        end = z3.Int(_symbol("end", task.task_id))
        starts[task.task_id] = start
        ends[task.task_id] = end
        assert task.release_slot is not None
        assert task.window_end_slot is not None
        assert task.window_constraint_id is not None
        add(start >= task.release_slot, task.window_constraint_id)
        add(end <= task.window_end_slot, task.window_constraint_id)
        add(end > start, task.window_constraint_id)

        if task.scheduling_kind in ("flexible_active", "review"):
            assert task.allowed_resource_ids is not None
            assert task.active_slots is not None
            assert task.effort_constraint_id is not None
            assert task.eligibility_constraint_id is not None
            assert task.segmentation_constraint_id is not None
            eligible_ids = tuple(sorted(task.allowed_resource_ids, key=str))
            for resource_id in eligible_ids:
                assignments[(task.task_id, resource_id)] = z3.Bool(
                    _symbol("assign", task.task_id, resource_id)
                )
            add(
                _bool_sum(assignments[(task.task_id, resource_id)] for resource_id in eligible_ids)
                == 1,
                task.eligibility_constraint_id,
            )

            task_variables: list[z3.BoolRef] = []
            for resource_id in eligible_ids:
                resource = normalized.resources[resource_id]
                owner = assignments[(task.task_id, resource_id)]
                for slot in range(task.release_slot, task.window_end_slot):
                    if slot not in resource.available_slots:
                        continue
                    variable = z3.Bool(_symbol("work", task.task_id, resource_id, slot))
                    occupancy[(task.task_id, resource_id, slot)] = variable
                    task_variables.append(variable)
                    add(z3.Implies(variable, owner), task.eligibility_constraint_id)
                    add(z3.Implies(variable, start <= slot), task.effort_constraint_id)
                    add(z3.Implies(variable, end >= slot + 1), task.effort_constraint_id)
            add(_bool_sum(task_variables) == task.active_slots, task.effort_constraint_id)
            add(
                z3.Or(
                    *(
                        z3.And(variable, start == slot)
                        for (task_id, _resource_id, slot), variable in occupancy.items()
                        if task_id == task.task_id
                    )
                ),
                task.effort_constraint_id,
            )
            add(
                z3.Or(
                    *(
                        z3.And(variable, end == slot + 1)
                        for (task_id, _resource_id, slot), variable in occupancy.items()
                        if task_id == task.task_id
                    )
                ),
                task.effort_constraint_id,
            )

            slots_per_day = max(1, 1_440 // snapshot.slot_minutes)
            for resource_id in eligible_ids:
                resource_variables = {
                    slot: variable
                    for (task_id, candidate_id, slot), variable in occupancy.items()
                    if task_id == task.task_id and candidate_id == resource_id
                }
                for slot, variable in resource_variables.items():
                    previous = resource_variables.get(slot - 1)
                    same_day = slot % slots_per_day != 0
                    segment_start = z3.Bool(_symbol("segment", task.task_id, resource_id, slot))
                    segment_starts[(task.task_id, resource_id, slot)] = segment_start
                    expression = (
                        z3.And(variable, z3.Not(previous))
                        if previous is not None and same_day
                        else variable
                    )
                    add(segment_start == expression, task.segmentation_constraint_id)
                    minimum = min(task.minimum_segment_slots or 1, task.active_slots)
                    required_slots = range(slot, slot + minimum)
                    required_variables = [
                        resource_variables.get(required) for required in required_slots
                    ]
                    if slot // slots_per_day != (slot + minimum - 1) // slots_per_day or any(
                        required is None for required in required_variables
                    ):
                        add(z3.Not(segment_start), task.segmentation_constraint_id)
                    else:
                        add(
                            z3.Implies(
                                segment_start,
                                z3.And(
                                    *(
                                        required
                                        for required in required_variables
                                        if required is not None
                                    )
                                ),
                            ),
                            task.segmentation_constraint_id,
                        )
                for day_index in range((snapshot.slot_count + slots_per_day - 1) // slots_per_day):
                    day_starts = [
                        variable
                        for (task_id, candidate_id, slot), variable in segment_starts.items()
                        if task_id == task.task_id
                        and candidate_id == resource_id
                        and slot // slots_per_day == day_index
                    ]
                    add(
                        _bool_sum(day_starts) <= (task.max_segments_per_day or 1),
                        task.segmentation_constraint_id,
                    )
            if not task.split_allowed:
                add(
                    _bool_sum(
                        variable
                        for (task_id, _resource_id, _slot), variable in segment_starts.items()
                        if task_id == task.task_id
                    )
                    <= 1,
                    task.segmentation_constraint_id,
                )

        elif task.scheduling_kind == "fixed_attendance":
            assert task.fixed_constraint_id is not None
            add(start == task.fixed_slots[0], task.fixed_constraint_id)
            add(end == task.fixed_slots[-1] + 1, task.fixed_constraint_id)
        else:
            assert task.elapsed_slots is not None
            assert task.effort_constraint_id is not None
            add(end == start + task.elapsed_slots, task.effort_constraint_id)

        if task.deadline is not None:
            assert task.deadline_constraint_id is not None
            if task.deadline.hard_finish_slot is not None:
                add(end <= task.deadline.hard_finish_slot, task.deadline_constraint_id)
            if task.deadline.max_authorized_finish_slot is not None:
                add(end <= task.deadline.max_authorized_finish_slot, task.deadline_constraint_id)

        should_pin = task.movement == "locked" or (
            scope == "pinned_insertion" and task.movement == "authorized"
        )
        if should_pin:
            assert task.movement_constraint_id is not None
            assert task.existing_resource_id is not None
            for resource_id in task.allowed_resource_ids or ():
                owner = assignments.get((task.task_id, resource_id))
                if owner is not None:
                    add(
                        owner == (resource_id == task.existing_resource_id),
                        task.movement_constraint_id,
                    )
            existing = set(task.existing_slots)
            for (task_id, resource_id, slot), variable in occupancy.items():
                if task_id == task.task_id:
                    expected = resource_id == task.existing_resource_id and slot in existing
                    add(variable == expected, task.movement_constraint_id)

    for dependency in normalized.dependencies:
        predecessor_task_ids = [dependency.predecessor_task_id]
        if dependency.acceptance_required:
            predecessor_task_ids = [
                review.review_task_id
                for review in normalized.reviews
                if review.reviewed_task_id == dependency.predecessor_task_id
            ]
        for predecessor_task_id in predecessor_task_ids:
            add(
                starts[dependency.successor_task_id]
                >= ends[predecessor_task_id] + dependency.minimum_lag_slots,
                dependency.constraint_id,
            )

    for review in normalized.reviews:
        add(
            starts[review.review_task_id] >= ends[review.reviewed_task_id],
            review.constraint_id,
        )
        if review.require_separate_resource:
            review_task = normalized.tasks[review.review_task_id]
            reviewed_task = normalized.tasks[review.reviewed_task_id]
            for resource_id in normalized.resources:
                reviewer = assignments.get((review_task.task_id, resource_id))
                owner = assignments.get((reviewed_task.task_id, resource_id))
                if reviewer is not None and owner is not None:
                    add(z3.Or(z3.Not(reviewer), z3.Not(owner)), review.constraint_id)
                elif reviewer is not None and resource_id in reviewed_task.fixed_resource_ids:
                    add(z3.Not(reviewer), review.constraint_id)

    reservation_usage: dict[tuple[UUID, int], int] = defaultdict(int)
    budget_reservation_usage: dict[tuple[UUID, int], int] = defaultdict(int)
    reservation_ids: dict[tuple[UUID, int], list[str]] = defaultdict(list)
    for reservation in normalized.reservations:
        for slot in reservation.slots:
            reservation_usage[(reservation.resource_id, slot)] += reservation.capacity_units
            reservation_ids[(reservation.resource_id, slot)].append(reservation.constraint_id)
            if reservation.consumes_daily_budget:
                budget_reservation_usage[(reservation.resource_id, slot)] += (
                    reservation.capacity_units
                )

    fixed_usage: dict[tuple[UUID, int], list[TaskSpec]] = defaultdict(list)
    for task in task_order:
        for resource_id in task.fixed_resource_ids:
            for slot in task.fixed_slots:
                fixed_usage[(resource_id, slot)].append(task)

    shared_active: dict[tuple[UUID, int], list[tuple[z3.BoolRef, int, str]]] = defaultdict(list)
    for task in task_order:
        if not task.shared_demands:
            continue
        if task.scheduling_kind in ("flexible_active", "review"):
            for slot in range(snapshot.slot_count):
                active_variables = [
                    variable
                    for (task_id, _resource_id, candidate_slot), variable in occupancy.items()
                    if task_id == task.task_id and candidate_slot == slot
                ]
                if not active_variables:
                    continue
                active = z3.Or(*active_variables)
                for demand in task.shared_demands:
                    shared_active[(demand.resource_id, slot)].append(
                        (
                            active,
                            demand.capacity_units,
                            task.shared_constraint_id or task.definition_constraint_id,
                        )
                    )
        elif task.scheduling_kind == "fixed_attendance":
            for slot in task.fixed_slots:
                for demand in task.shared_demands:
                    shared_active[(demand.resource_id, slot)].append(
                        (
                            z3.BoolVal(True),
                            demand.capacity_units,
                            task.shared_constraint_id or task.definition_constraint_id,
                        )
                    )

    for resource_id, resource in normalized.resources.items():
        for slot in range(snapshot.slot_count):
            terms: list[z3.ArithRef] = []
            constraint_ids: list[str] = [resource.constraint_id]
            if resource.resource_kind == "human":
                for (task_id, candidate_resource_id, candidate_slot), variable in occupancy.items():
                    if candidate_resource_id == resource_id and candidate_slot == slot:
                        terms.append(z3.If(variable, 1, 0))
                        constraint_ids.extend(normalized.tasks[task_id].constraint_ids)
                if fixed_usage[(resource_id, slot)]:
                    terms.append(z3.IntVal(len(fixed_usage[(resource_id, slot)])))
                    constraint_ids.extend(
                        task.fixed_constraint_id or task.definition_constraint_id
                        for task in fixed_usage[(resource_id, slot)]
                    )
            for active, units, constraint_id in shared_active[(resource_id, slot)]:
                terms.append(z3.If(active, units, 0))
                constraint_ids.append(constraint_id)
                if slot not in resource.available_slots:
                    add(z3.Not(active), constraint_id)
            occupied = reservation_usage[(resource_id, slot)]
            if occupied:
                terms.append(z3.IntVal(occupied))
                constraint_ids.extend(reservation_ids[(resource_id, slot)])
            add(_sum(terms) <= resource.capacity_per_slot, sorted(set(constraint_ids))[0])

        slots_per_day = max(1, 1_440 // snapshot.slot_minutes)
        for day_index, budget in resource.daily_budgets.items():
            terms = []
            for slot in range(snapshot.slot_count):
                if slot // slots_per_day != day_index:
                    continue
                if resource.resource_kind == "human":
                    terms.extend(
                        z3.If(variable, 1, 0)
                        for (_task_id, candidate_id, candidate_slot), variable in occupancy.items()
                        if candidate_id == resource_id and candidate_slot == slot
                    )
                    if fixed_usage[(resource_id, slot)]:
                        terms.append(z3.IntVal(len(fixed_usage[(resource_id, slot)])))
                terms.extend(
                    z3.If(active, units, 0)
                    for active, units, _constraint_id in shared_active[(resource_id, slot)]
                )
                if budget_reservation_usage[(resource_id, slot)]:
                    terms.append(z3.IntVal(budget_reservation_usage[(resource_id, slot)]))
            add(_sum(terms) <= budget, resource.constraint_id)

    objective_specs: list[tuple[str, z3.ArithRef]] = []
    priority_tiers = sorted({task.priority_tier for task in task_order})
    for tier in priority_tiers:
        tier_tasks = [task for task in task_order if task.priority_tier == tier]
        lateness: list[z3.ArithRef] = []
        completion: list[z3.ArithRef] = []
        for task in tier_tasks:
            deadline = task.deadline
            target = None
            if deadline is not None:
                target = deadline.agreed_finish_slot or deadline.requested_finish_slot
            if target is not None:
                lateness.append(z3.If(ends[task.task_id] > target, ends[task.task_id] - target, 0))
            completion.append(ends[task.task_id])
        objective_specs.append((f"tier_{tier}_lateness", _sum(lateness)))
        objective_specs.append((f"tier_{tier}_completion", _sum(completion)))

    owner_changes: list[z3.ArithRef] = []
    displacement: list[z3.ArithRef] = []
    for task in task_order:
        if task.movement != "authorized" or task.existing_resource_id is None:
            continue
        existing_owner = assignments.get((task.task_id, task.existing_resource_id))
        if existing_owner is not None:
            owner_changes.append(z3.If(existing_owner, 0, 1))
        existing_slots = set(task.existing_slots)
        for (task_id, resource_id, slot), variable in occupancy.items():
            if task_id != task.task_id:
                continue
            expected = resource_id == task.existing_resource_id and slot in existing_slots
            displacement.append(z3.If(variable == expected, 0, 1))
    objective_specs.append(("owner_changes", _sum(owner_changes)))
    objective_specs.append(("slot_displacement", _sum(displacement)))
    objective_specs.append(("fragmentation", _bool_sum(segment_starts.values())))

    for task in task_order:
        objective_specs.append((f"task_{task.task_key}_start", starts[task.task_id]))
        owner_rank = _sum(
            z3.If(assignments[(task.task_id, resource_id)], index, 0)
            for index, resource_id in enumerate(sorted(task.allowed_resource_ids or (), key=str))
            if (task.task_id, resource_id) in assignments
        )
        objective_specs.append((f"task_{task.task_key}_owner_rank", owner_rank))
        slot_rank = _sum(
            z3.If(variable, slot + 1, 0)
            for (task_id, _resource_id, slot), variable in occupancy.items()
            if task_id == task.task_id
        )
        objective_specs.append((f"task_{task.task_key}_slot_rank", slot_rank))

    objectives: list[ObjectiveExpression] = []
    for name, expression in objective_specs:
        objectives.append(
            ObjectiveExpression(
                name=name, expression=expression, handle=optimizer.minimize(expression)
            )
        )

    boolean_count = len(assignments) + len(occupancy) + len(segment_starts)
    model_payload = {
        "snapshot_digest": snapshot.snapshot_digest,
        "compiler_version": COMPILER_VERSION,
        "scope": scope,
        "constraint_ids": list(normalized.constraint_ids),
        "task_count": len(normalized.tasks),
        "resource_count": len(normalized.resources),
        "slot_count": snapshot.slot_count,
        "boolean_variable_count": boolean_count,
    }
    metadata = CompiledModel(
        snapshot_digest=snapshot.snapshot_digest,
        model_digest=canonical_digest(model_payload),
        compiler_version=COMPILER_VERSION,
        scope=scope,
        constraint_ids=normalized.constraint_ids,
        task_count=len(normalized.tasks),
        resource_count=len(normalized.resources),
        slot_count=snapshot.slot_count,
        boolean_variable_count=boolean_count,
    )
    return CompiledZ3Problem(
        normalized=normalized,
        metadata=metadata,
        optimizer=optimizer,
        assignments=assignments,
        occupancy=occupancy,
        starts=starts,
        ends=ends,
        segment_starts=segment_starts,
        hard_assertions=dict(hard_assertions),
        objectives=objectives,
    )


def objective_values(problem: CompiledZ3Problem, model: z3.ModelRef) -> tuple[ObjectiveValue, ...]:
    return tuple(
        ObjectiveValue(name=objective.name, value=model.eval(objective.expression).as_long())
        for objective in problem.objectives
    )


def optimization_is_proven(problem: CompiledZ3Problem) -> bool:
    return all(
        str(objective.handle.lower()) == str(objective.handle.upper())
        for objective in problem.objectives
    )


def extract_schedule(
    problem: CompiledZ3Problem,
    model: z3.ModelRef,
) -> tuple[tuple[TaskPlacement, ...], tuple[ScheduleBlock, ...]]:
    placements: list[TaskPlacement] = []
    blocks: list[ScheduleBlock] = []
    tasks = sorted(
        problem.normalized.tasks.values(), key=lambda task: (task.task_key, str(task.task_id))
    )
    for task in tasks:
        start = model.eval(problem.starts[task.task_id]).as_long()
        end = model.eval(problem.ends[task.task_id]).as_long()
        owner_id: UUID | None = None
        occupied_slots: list[int] = []
        if task.scheduling_kind in ("flexible_active", "review"):
            for resource_id in sorted(task.allowed_resource_ids or (), key=str):
                assignment = problem.assignments[(task.task_id, resource_id)]
                if z3.is_true(model.eval(assignment)):
                    owner_id = resource_id
                    occupied_slots = sorted(
                        slot
                        for (task_id, candidate_id, slot), variable in problem.occupancy.items()
                        if task_id == task.task_id
                        and candidate_id == resource_id
                        and z3.is_true(model.eval(variable))
                    )
                    for block_start, block_end in _contiguous_blocks(occupied_slots):
                        blocks.append(
                            ScheduleBlock(
                                task_id=task.task_id,
                                resource_id=resource_id,
                                start_slot=block_start,
                                end_slot=block_end,
                                capacity_units=1,
                                role="owner",
                            )
                        )
                    break
        elif task.scheduling_kind == "fixed_attendance":
            occupied_slots = list(task.fixed_slots)
            for resource_id in sorted(task.fixed_resource_ids, key=str):
                for block_start, block_end in _contiguous_blocks(occupied_slots):
                    blocks.append(
                        ScheduleBlock(
                            task_id=task.task_id,
                            resource_id=resource_id,
                            start_slot=block_start,
                            end_slot=block_end,
                            capacity_units=1,
                            role="participant",
                        )
                    )
        placements.append(
            TaskPlacement(
                task_id=task.task_id,
                start_slot=start,
                end_slot=end,
                owner_resource_id=owner_id,
            )
        )
        if task.shared_demands:
            for demand in task.shared_demands:
                for block_start, block_end in _contiguous_blocks(occupied_slots):
                    blocks.append(
                        ScheduleBlock(
                            task_id=task.task_id,
                            resource_id=demand.resource_id,
                            start_slot=block_start,
                            end_slot=block_end,
                            capacity_units=demand.capacity_units,
                            role="shared",
                        )
                    )
    return (
        tuple(sorted(placements, key=lambda item: str(item.task_id))),
        tuple(
            sorted(
                blocks,
                key=lambda item: (
                    str(item.task_id),
                    str(item.resource_id),
                    item.start_slot,
                    item.role,
                ),
            )
        ),
    )


def diagnose_unsat(problem: CompiledZ3Problem) -> tuple[str, ...]:
    snapshot = problem.normalized.snapshot
    solver = z3.Solver()
    solver.set(timeout=snapshot.policy.timeout_ms, rlimit=snapshot.policy.resource_limit)
    tracked: dict[str, str] = {}
    for index, (constraint_id, assertions) in enumerate(sorted(problem.hard_assertions.items())):
        symbol = f"tracked_{index}"
        tracked[symbol] = constraint_id
        solver.assert_and_track(z3.And(*assertions), z3.Bool(symbol))
    if solver.check() != z3.unsat:
        return ()
    return tuple(sorted(tracked[str(symbol)] for symbol in solver.unsat_core()))
