"""Check an already complete candidate; this module never constructs a schedule.

Z3 sees ground integer/boolean expressions. There are no free owner/time variables,
Optimize calls, model extraction, or automatic repair paths in this compiler.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Literal
from uuid import UUID

import z3  # type: ignore[import-untyped]

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
    ScheduleBlock,
    SegmentationPayload,
    SharedResourcePayload,
    TaskDefinitionPayload,
    TaskPlacement,
    TaskReviewPolicyPayload,
    ValidationIssue,
    WorkingWindowPayload,
    canonical_digest,
)
from coordination.planning.fixed_contracts import (
    FixedCandidateResult,
    FixedCheckReport,
    FixedRuleResult,
    FixedValidationReport,
    PlanProposalV2,
    RuleCategoryKey,
    rule_categories_for_family,
)
from coordination.planning.normalizer import NormalizedPlanningModel, normalize_snapshot
from coordination.planning.validator import validate_schedule

FIXED_COMPILER_VERSION = "alto-fixed-candidate-compiler.v1"
FIXED_VERIFIER_VERSION = "alto-fixed-candidate-verifier.v3"
FIXED_VALIDATOR_VERSION = "alto-fixed-candidate-validator.v1"


class CandidateAdmissionError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        super().__init__("complete candidate failed trusted admission")
        self.issues = issues


def _issue(code: str, message: str, *rules: str) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, constraint_ids=tuple(rules))


def _slot(snapshot: PlanningSnapshot, instant: datetime) -> int:
    seconds = (instant.astimezone(UTC) - snapshot.horizon_start.astimezone(UTC)).total_seconds()
    width = snapshot.slot_minutes * 60
    if seconds < 0 or seconds % width or seconds > snapshot.slot_count * width:
        raise ValueError("candidate instant is outside the horizon or not exactly slot aligned")
    return int(seconds // width)


def admit_candidate(
    snapshot: PlanningSnapshot,
    proposal: PlanProposalV2,
) -> tuple[NormalizedPlanningModel, tuple[TaskPlacement, ...], tuple[ScheduleBlock, ...]]:
    """Reject untrusted identity/evidence/time shape before constructing any Z3 input."""
    issues: list[ValidationIssue] = []
    if (
        proposal.company_id != snapshot.company_id
        or proposal.request_id != snapshot.request_id
        or proposal.snapshot_id != snapshot.snapshot_id
        or proposal.snapshot_digest != snapshot.snapshot_digest
        or proposal.source_manifest_digest != snapshot.source_manifest_digest
        or proposal.candidate_digest != proposal.draft.semantic_digest
        or snapshot.snapshot_digest != canonical_digest(snapshot.digest_payload())
    ):
        raise CandidateAdmissionError(
            (_issue("binding_mismatch", "immutable candidate context changed"),)
        )
    if proposal.draft.unresolved_items or proposal.draft.assumptions:
        issues.append(
            _issue("unresolved_authority", "material assumptions require admission before planning")
        )
    normalized = normalize_snapshot(snapshot)
    task_map = {task.task_id: task for task in proposal.draft.tasks}
    if len(task_map) != len(proposal.draft.tasks) or set(task_map) != set(normalized.tasks):
        raise CandidateAdmissionError(
            (
                _issue(
                    "task_set_mismatch", "candidate must contain every admitted task exactly once"
                ),
            )
        )
    rules = {rule.constraint_id: rule for rule in snapshot.constraints}
    placements: list[TaskPlacement] = []
    blocks: list[ScheduleBlock] = []
    for task in proposal.draft.tasks:
        spec = normalized.tasks[task.task_id]
        if (task.task_key, task.title, task.scheduling_kind) != (
            spec.task_key,
            spec.title,
            spec.scheduling_kind,
        ):
            issues.append(
                _issue(
                    "task_identity_changed",
                    "candidate changed an admitted task definition",
                    spec.definition_constraint_id,
                )
            )
        if (
            not set(task.evidence_rule_ids) <= rules.keys()
            or spec.definition_constraint_id not in task.evidence_rule_ids
        ):
            issues.append(
                _issue(
                    "invalid_evidence",
                    "task evidence must cite supplied admitted rule IDs",
                    spec.definition_constraint_id,
                )
            )
        if (
            any(
                rules[rule_id].confidentiality == "restricted"
                for rule_id in task.evidence_rule_ids
                if rule_id in rules
            )
            and task.confidentiality != "restricted"
        ):
            issues.append(
                _issue(
                    "confidentiality_widened",
                    "restricted evidence cannot be reclassified as company-visible",
                    spec.definition_constraint_id,
                )
            )
        declared_people = (*task.reviewer_resource_ids, *task.audience_resource_ids)
        if task.owner_resource_id is not None:
            declared_people = (*declared_people, task.owner_resource_id)
        if any(
            person not in normalized.resources
            or normalized.resources[person].resource_kind != "human"
            for person in declared_people
        ):
            issues.append(
                _issue(
                    "unknown_person",
                    "candidate refers to a person outside its authorised finite domain",
                    spec.definition_constraint_id,
                )
            )
        expected_reviewers = {
            task_map[review.review_task_id].owner_resource_id
            for review in normalized.reviews
            if review.reviewed_task_id == task.task_id
        }
        if expected_reviewers:
            if (
                task.review_policy != "exact_review"
                or set(task.reviewer_resource_ids) != expected_reviewers
            ):
                issues.append(
                    _issue(
                        "review_policy_changed",
                        "candidate must retain the exact admitted review policy",
                        spec.definition_constraint_id,
                    )
                )
        elif task.review_policy == "exact_review" or task.reviewer_resource_ids:
            issues.append(
                _issue(
                    "unadmitted_review",
                    "review work must be admitted and reserved as a separate task",
                    spec.definition_constraint_id,
                )
            )
        if spec.review_policy is not None and task.review_policy != spec.review_policy.policy:
            issues.append(
                _issue(
                    "review_policy_authority_changed",
                    "task review policy differs from its admitted authority",
                    spec.review_policy_constraint_id or spec.definition_constraint_id,
                )
            )
        if spec.review_policy is None and task.review_policy == "self_certifiable_internal_draft":
            issues.append(
                _issue(
                    "unadmitted_self_certification",
                    "self certification requires an explicit admitted policy",
                    spec.definition_constraint_id,
                )
            )
        try:
            start, end = _slot(snapshot, task.start), _slot(snapshot, task.end)
            placements.append(
                TaskPlacement(
                    task_id=task.task_id,
                    start_slot=start,
                    end_slot=end,
                    owner_resource_id=task.owner_resource_id,
                )
            )
            for block in task.blocks:
                if block.resource_id not in normalized.resources:
                    raise ValueError("unknown block resource")
                blocks.append(
                    ScheduleBlock(
                        task_id=task.task_id,
                        resource_id=block.resource_id,
                        start_slot=_slot(snapshot, block.start),
                        end_slot=_slot(snapshot, block.end),
                        capacity_units=block.capacity_units,
                        role=block.role,
                    )
                )
        except ValueError:
            issues.append(
                _issue(
                    "invalid_exact_time",
                    "candidate blocks require authorised resources and exact aligned instants",
                    spec.definition_constraint_id,
                )
            )
    gates = {gate.rule_id: gate for gate in proposal.draft.gates}
    explicit_gates = {
        rule.constraint_id: rule.payload
        for rule in snapshot.constraints
        if isinstance(rule.payload, ExecutionGatePayload)
    }
    if len(gates) != len(proposal.draft.gates) or set(gates) != (
        {edge.constraint_id for edge in normalized.dependencies} | explicit_gates.keys()
    ):
        issues.append(
            _issue(
                "gate_set_mismatch",
                "candidate must preserve every admitted dependency gate exactly once",
            )
        )
    for dependency in normalized.dependencies:
        gate = gates.get(dependency.constraint_id)
        if gate is None:
            continue
        expected_reviews = (
            {
                review.review_task_id
                for review in normalized.reviews
                if review.reviewed_task_id == dependency.predecessor_task_id
            }
            if dependency.acceptance_required
            else set()
        )
        if (
            gate.predecessor_task_id != dependency.predecessor_task_id
            or gate.successor_task_id != dependency.successor_task_id
            or gate.required_state
            != ("accepted" if dependency.acceptance_required else "submitted")
            or gate.minimum_lag_minutes != dependency.minimum_lag_slots * snapshot.slot_minutes
            or set(gate.review_task_ids) != expected_reviews
        ):
            issues.append(
                _issue(
                    "gate_authority_changed",
                    "candidate changed an admitted predecessor, review, state or lag",
                    dependency.constraint_id,
                )
            )
    for rule_id, admitted_gate in explicit_gates.items():
        gate = gates.get(rule_id)
        if gate is not None and (
            gate.predecessor_task_id != admitted_gate.predecessor_task_id
            or gate.successor_task_id != admitted_gate.successor_task_id
            or gate.required_state != admitted_gate.required_state
            or gate.minimum_lag_minutes != admitted_gate.minimum_lag_slots * snapshot.slot_minutes
            or gate.review_task_ids
        ):
            issues.append(
                _issue(
                    "execution_gate_changed",
                    "explicit decision/artifact gate differs from its admitted rule",
                    rule_id,
                )
            )
    if issues:
        raise CandidateAdmissionError(tuple(issues))
    return normalized, tuple(placements), tuple(blocks)


def _ground_rules(
    normalized: NormalizedPlanningModel,
    proposal: PlanProposalV2,
    placements: tuple[TaskPlacement, ...],
    blocks: tuple[ScheduleBlock, ...],
) -> dict[str, list[z3.BoolRef]]:
    """Each expression depends only on exact submitted values and frozen policy."""
    snapshot = normalized.snapshot
    placed = {item.task_id: item for item in placements}
    proposed = {item.task_id: item for item in proposal.draft.tasks}
    by_task: dict[UUID, list[ScheduleBlock]] = defaultdict(list)
    usage: Counter[tuple[UUID, int]] = Counter()
    budget_usage: Counter[tuple[UUID, int]] = Counter()
    for block in blocks:
        by_task[block.task_id].append(block)
        for slot in range(block.start_slot, block.end_slot):
            usage[block.resource_id, slot] += block.capacity_units
            budget_usage[block.resource_id, slot] += block.capacity_units
    for reservation in normalized.reservations:
        for slot in reservation.slots:
            usage[reservation.resource_id, slot] += reservation.capacity_units
            if reservation.consumes_daily_budget:
                budget_usage[reservation.resource_id, slot] += reservation.capacity_units
    rules: dict[str, list[z3.BoolRef]] = {}

    def iv(value: int) -> z3.ArithRef:
        return z3.IntVal(value)

    def bv(value: bool) -> z3.BoolRef:
        return z3.BoolVal(value)

    def active(task_id: UUID, role: str = "owner") -> list[int]:
        return [
            slot
            for block in by_task[task_id]
            if block.role == role
            for slot in range(block.start_slot, block.end_slot)
        ]

    def same_slots(actual: list[int], expected: tuple[int, ...] | list[int]) -> z3.BoolRef:
        return bv(sorted(actual) == sorted(expected))

    for rule in snapshot.constraints:
        payload = rule.payload
        expressions: list[z3.BoolRef] = []
        task_id = getattr(payload, "task_id", None)
        placement = placed.get(task_id) if task_id is not None else None
        task = normalized.tasks.get(task_id) if task_id is not None else None
        if isinstance(payload, TaskDefinitionPayload):
            value = proposed[payload.task_id]
            expressions = [
                bv(value.scheduling_kind == payload.scheduling_kind),
                iv(placed[payload.task_id].end_slot) > iv(placed[payload.task_id].start_slot),
            ]
        elif isinstance(payload, ResourceCapacityPayload):
            expressions = [
                iv(usage[payload.resource_id, slot]) <= iv(payload.capacity_per_slot)
                for slot in range(snapshot.slot_count)
            ]
            allowed = set(payload.available_slots)
            expressions += [
                bv(slot in allowed)
                for block in blocks
                if block.resource_id == payload.resource_id
                for slot in range(block.start_slot, block.end_slot)
            ]
            # Daily budgets use each resource's local date, not UTC midnight.
            from datetime import timedelta
            from zoneinfo import ZoneInfo

            zone = ZoneInfo(payload.timezone)
            first_day = snapshot.horizon_start.astimezone(zone).date()
            for budget in payload.daily_budgets:
                consumed = sum(
                    units
                    for (resource_id, slot), units in budget_usage.items()
                    if resource_id == payload.resource_id
                    and (
                        (
                            snapshot.horizon_start.astimezone(UTC)
                            + timedelta(minutes=slot * snapshot.slot_minutes)
                        )
                        .astimezone(zone)
                        .date()
                        - first_day
                    ).days
                    == budget.day_index
                )
                expressions.append(iv(consumed) <= iv(budget.max_active_slots))
        elif isinstance(payload, EffortPayload) and placement is not None and task is not None:
            value = proposed[payload.task_id]
            slots = active(payload.task_id)
            if task.scheduling_kind == "passive_wait":
                expressions = [
                    iv(placement.end_slot) - iv(placement.start_slot) == iv(payload.elapsed_slots),
                    iv(value.effort_minutes) == 0,
                    bv(not by_task[payload.task_id]),
                ]
            elif task.scheduling_kind == "fixed_attendance":
                expressions = [
                    iv(value.effort_minutes) == iv(payload.active_slots * snapshot.slot_minutes)
                ]
            else:
                expressions = [
                    iv(len(slots)) == iv(payload.active_slots),
                    bv(len(slots) == len(set(slots))),
                    iv(value.effort_minutes) == iv(payload.active_slots * snapshot.slot_minutes),
                    bv(
                        bool(slots)
                        and min(slots) == placement.start_slot
                        and max(slots) + 1 == placement.end_slot
                    ),
                ]
        elif isinstance(payload, EligibilityPayload) and placement is not None:
            expressions = [
                z3.Sum(
                    [
                        z3.If(bv(placement.owner_resource_id == owner), 1, 0)
                        for owner in payload.allowed_resource_ids
                    ]
                )
                == 1
            ]
            expressions += [
                bv(block.resource_id == placement.owner_resource_id and block.capacity_units == 1)
                for block in by_task[payload.task_id]
                if block.role == "owner"
            ]
        elif isinstance(payload, WorkingWindowPayload) and placement is not None:
            expressions = [
                iv(placement.start_slot) >= iv(payload.release_slot),
                iv(placement.end_slot) <= iv(payload.end_slot),
            ]
        elif isinstance(payload, ActiveParticipantsPayload) and placement is not None:
            people = set(payload.participant_resource_ids) - {placement.owner_resource_id}
            participant_blocks = [
                block for block in by_task[payload.task_id] if block.role == "participant"
            ]
            expressions = [bv({block.resource_id for block in participant_blocks} == people)]
            for person in people:
                actual = [
                    slot
                    for block in participant_blocks
                    if block.resource_id == person
                    for slot in range(block.start_slot, block.end_slot)
                ]
                expressions.append(same_slots(actual, active(payload.task_id)))
            expressions += [iv(block.capacity_units) == 1 for block in participant_blocks]
        elif isinstance(payload, FixedAttendancePayload) and placement is not None:
            expressions = [
                iv(placement.start_slot) == iv(payload.slots[0]),
                iv(placement.end_slot) == iv(payload.slots[-1] + 1),
                bv(placement.owner_resource_id in (None, *payload.participant_resource_ids)),
            ]
            participants = [
                block for block in by_task[payload.task_id] if block.role == "participant"
            ]
            expressions += [
                bv(
                    {block.resource_id for block in participants}
                    == set(payload.participant_resource_ids)
                ),
                bv(not any(block.role == "owner" for block in by_task[payload.task_id])),
            ]
            for person in payload.participant_resource_ids:
                expressions.append(
                    same_slots(
                        [
                            slot
                            for block in participants
                            if block.resource_id == person
                            for slot in range(block.start_slot, block.end_slot)
                        ],
                        payload.slots,
                    )
                )
            expressions += [iv(block.capacity_units) == 1 for block in participants]
        elif isinstance(payload, DependencyPayload):
            predecessors = [placed[payload.predecessor_task_id]]
            if payload.acceptance_required:
                predecessors = [
                    placed[review.review_task_id]
                    for review in normalized.reviews
                    if review.reviewed_task_id == payload.predecessor_task_id
                ]
            expressions = [
                iv(placed[payload.successor_task_id].start_slot)
                >= iv(predecessor.end_slot) + iv(payload.minimum_lag_slots)
                for predecessor in predecessors
            ]
        elif isinstance(payload, ReviewPayload):
            reviewer, reviewed = placed[payload.review_task_id], placed[payload.reviewed_task_id]
            expressions = [iv(reviewer.start_slot) >= iv(reviewed.end_slot)]
            if payload.require_separate_resource:
                expressions.append(
                    bv(
                        reviewer.owner_resource_id
                        not in {
                            block.resource_id
                            for block in by_task[payload.reviewed_task_id]
                            if block.role in ("owner", "participant")
                        }
                    )
                )
        elif isinstance(payload, ExecutionGatePayload):
            expressions = [
                iv(placed[payload.successor_task_id].start_slot)
                >= iv(placed[payload.predecessor_task_id].end_slot) + iv(payload.minimum_lag_slots)
            ]
        elif isinstance(payload, TaskReviewPolicyPayload):
            expressions = [
                bv(proposed[payload.task_id].review_policy == payload.policy),
                bv(
                    set(proposed[payload.task_id].reviewer_resource_ids)
                    == {
                        placed[review_id].owner_resource_id for review_id in payload.review_task_ids
                    }
                ),
            ]
        elif isinstance(payload, DeadlinePayload) and placement is not None:
            # Requested and forecast dates are reported facts, not implicit hard dates.
            expressions = [
                iv(placement.end_slot) <= iv(limit)
                for limit in (payload.hard_finish_slot, payload.max_authorized_finish_slot)
                if limit is not None
            ]
            if not expressions and rule.strength == "preferred":
                expressions = [bv(True)]
        elif isinstance(payload, ReservationPayload):
            capacity = normalized.resources[payload.resource_id].capacity_per_slot
            expressions = [
                iv(usage[payload.resource_id, slot]) <= iv(capacity) for slot in payload.slots
            ]
        elif isinstance(payload, SharedResourcePayload):
            expected = set(active(payload.task_id) or active(payload.task_id, "participant"))
            shared = [block for block in by_task[payload.task_id] if block.role == "shared"]
            expressions = [
                bv(
                    {block.resource_id for block in shared}
                    == {d.resource_id for d in payload.demands}
                )
            ]
            for demand in payload.demands:
                actual = [
                    slot
                    for block in shared
                    if block.resource_id == demand.resource_id
                    for slot in range(block.start_slot, block.end_slot)
                ]
                expressions += [same_slots(actual, sorted(expected))]
                expressions += [
                    iv(block.capacity_units) == iv(demand.capacity_units)
                    for block in shared
                    if block.resource_id == demand.resource_id
                ]
        elif isinstance(payload, SegmentationPayload):
            slots = sorted(set(active(payload.task_id)))
            from datetime import timedelta
            from zoneinfo import ZoneInfo

            owner_id = placed[payload.task_id].owner_resource_id
            zone = ZoneInfo(
                normalized.resources[owner_id].timezone
                if owner_id is not None
                else proposal.draft.timezone
            )

            def local_day(slot: int, zone: ZoneInfo = zone) -> object:
                return (
                    (
                        snapshot.horizon_start.astimezone(UTC)
                        + timedelta(minutes=slot * snapshot.slot_minutes)
                    )
                    .astimezone(zone)
                    .date()
                )

            segments: list[list[int]] = []
            for slot in slots:
                if (
                    not segments
                    or slot != segments[-1][-1] + 1
                    or local_day(slot) != local_day(segments[-1][-1])
                ):
                    segments.append([])
                segments[-1].append(slot)
            counts = Counter(local_day(segment[0]) for segment in segments)
            expressions = [bv(payload.split_allowed or len(segments) <= 1)]
            expressions += [
                iv(len(segment)) >= iv(min(payload.minimum_segment_slots, len(slots)))
                for segment in segments
            ]
            expressions += [
                iv(count) <= iv(payload.max_segments_per_day) for count in counts.values()
            ]
        elif isinstance(payload, MovementPayload) and placement is not None:
            if payload.movement == "locked":
                expressions = [
                    bv(placement.owner_resource_id == payload.existing_resource_id),
                    same_slots(active(payload.task_id), payload.existing_slots),
                ]
            else:
                # The admitted movement enum is the trusted authorisation envelope.
                expressions = [bv(payload.movement in ("new", "authorized"))]
        elif isinstance(payload, PriorityPayload):
            # Preserve the admitted priority fact without optimising or granting authority.
            expressions = [iv(proposed[payload.task_id].priority_tier) == iv(payload.tier)]
        if expressions:
            rules[rule.constraint_id] = expressions
    return rules


def _slot_instant(snapshot: PlanningSnapshot, slot: int, timezone: str) -> str:
    from zoneinfo import ZoneInfo

    return (
        snapshot.horizon_start.astimezone(UTC)
        + timedelta(minutes=slot * snapshot.slot_minutes)
    ).astimezone(ZoneInfo(timezone)).isoformat()


def _rule_categories(
    snapshot: PlanningSnapshot, rule_id: str
) -> tuple[tuple[RuleCategoryKey, ...], tuple[str, ...]]:
    payload = next(
        rule.payload for rule in snapshot.constraints if rule.constraint_id == rule_id
    )
    return rule_categories_for_family(payload.family)


def _fixed_candidate_values(
    *,
    normalized: NormalizedPlanningModel,
    proposal: PlanProposalV2,
    rule_id: str,
    placements: tuple[TaskPlacement, ...],
    blocks: tuple[ScheduleBlock, ...],
) -> dict[str, object]:
    """Create bounded display bindings from the exact values supplied to the checker."""
    snapshot = normalized.snapshot
    rule = next(item for item in snapshot.constraints if item.constraint_id == rule_id)
    payload = rule.payload
    proposed = {item.task_id: item for item in proposal.draft.tasks}
    placed = {item.task_id: item for item in placements}

    def interval(start_slot: int, end_slot: int) -> dict[str, object]:
        return {
            "start_at": _slot_instant(snapshot, start_slot, proposal.draft.timezone),
            "end_at": _slot_instant(snapshot, end_slot, proposal.draft.timezone),
            "interval_semantics": "half-open",
        }

    def task_binding(task_id: UUID) -> dict[str, object]:
        task = proposed[task_id]
        placement = placed[task_id]
        return {
            "task_id": str(task_id),
            "task_key": task.task_key.upper(),
            "title": task.title,
            "owner_resource_id": str(placement.owner_resource_id)
            if placement.owner_resource_id is not None
            else None,
            "effort_minutes": task.effort_minutes,
            **interval(placement.start_slot, placement.end_slot),
        }

    values: dict[str, object] = {
        "admitted_rule": payload.model_dump(mode="json"),
        "rule_id": rule_id,
    }
    task_id = getattr(payload, "task_id", None)
    if task_id in proposed:
        values["task"] = task_binding(task_id)
        values["blocks"] = [
            {
                "resource_id": str(block.resource_id),
                "role": block.role,
                "capacity_units": block.capacity_units,
                **interval(block.start_slot, block.end_slot),
            }
            for block in blocks
            if block.task_id == task_id
        ]
    if isinstance(payload, ReservationPayload):
        protected_start, protected_end = min(payload.slots), max(payload.slots) + 1
        touching = [
            block
            for block in blocks
            if block.resource_id == payload.resource_id
            and block.end_slot >= protected_start
            and block.start_slot <= protected_end
        ]
        values.update(
            {
                "resource_id": str(payload.resource_id),
                "resource_label": rule_id.split(".")[1].title()
                if rule_id.startswith("protected.") and len(rule_id.split(".")) > 1
                else None,
                "protected_interval": interval(protected_start, protected_end),
                "candidate_intervals": [
                    {
                        **task_binding(block.task_id),
                        "role": block.role,
                        "capacity_units": block.capacity_units,
                    }
                    for block in touching
                ],
                "overlap": any(
                    block.start_slot < protected_end and protected_start < block.end_slot
                    for block in touching
                ),
            }
        )
    for key in (
        "predecessor_task_id",
        "successor_task_id",
        "reviewed_task_id",
        "review_task_id",
    ):
        related_task_id = getattr(payload, key, None)
        if related_task_id in proposed:
            values[key.removesuffix("_id")] = task_binding(related_task_id)
    return values


def independently_validate_candidate(
    snapshot: PlanningSnapshot,
    proposal: PlanProposalV2,
    normalized: NormalizedPlanningModel,
    placements: tuple[TaskPlacement, ...],
    blocks: tuple[ScheduleBlock, ...],
) -> FixedValidationReport:
    """No Z3 assertions/results are consulted by this separate concrete pass."""
    # Legacy validator treats fixed attendance as participant-owned. Preserve the
    # proposal's accountable owner while validating its participant reservations.
    projected = tuple(
        item.model_copy(update={"owner_resource_id": None})
        if normalized.tasks[item.task_id].scheduling_kind == "fixed_attendance"
        else item
        for item in placements
    )
    report = validate_schedule(
        normalized, scope="authorized_repair", placements=projected, blocks=blocks
    )
    issues = list(report.issues)
    placement_map = {item.task_id: item for item in placements}
    width = snapshot.slot_minutes * 60
    for task in proposal.draft.tasks:
        item = placement_map[task.task_id]
        for instant, slot in ((task.start, item.start_slot), (task.end, item.end_slot)):
            elapsed = instant.astimezone(UTC) - snapshot.horizon_start.astimezone(UTC)
            if elapsed.total_seconds() != slot * width:
                issues.append(
                    _issue(
                        "exact_time_changed",
                        "concrete placement differs from the original exact instant",
                    )
                )
        owner_seconds = sum(
            (block.end.astimezone(UTC) - block.start.astimezone(UTC)).total_seconds()
            for block in task.blocks
            if block.role == "owner"
        )
        if (
            task.scheduling_kind in ("flexible_active", "review")
            and owner_seconds != task.effort_minutes * 60
        ):
            issues.append(
                _issue(
                    "exact_effort_changed", "concrete intervals differ from exact authored effort"
                )
            )
        for block in task.blocks:
            if block.start.astimezone(UTC) < task.start.astimezone(UTC) or block.end.astimezone(
                UTC
            ) > task.end.astimezone(UTC):
                issues.append(
                    _issue("block_outside_task", "active reservation exceeds its task interval")
                )
    if (
        proposal.candidate_digest != proposal.draft.semantic_digest
        or snapshot.snapshot_digest != canonical_digest(snapshot.digest_payload())
    ):
        issues.append(
            _issue("digest_changed", "immutable semantic binding changed during validation")
        )
    return FixedValidationReport(
        validator_version=FIXED_VALIDATOR_VERSION,
        candidate_digest=proposal.draft.semantic_digest,
        snapshot_digest=snapshot.snapshot_digest,
        passed=not issues,
        issues=tuple(issues),
    )


def verify_fixed_candidate(
    snapshot: PlanningSnapshot, proposal: PlanProposalV2, *, max_timeout_ms: int | None = None
) -> FixedCandidateResult:
    started = monotonic()
    before = proposal.draft.semantic_digest
    required = tuple(
        sorted(rule.constraint_id for rule in snapshot.constraints if rule.strength == "hard")
    )
    covered: tuple[str, ...] = ()
    diagnostics: tuple[ValidationIssue, ...] = ()
    core: tuple[str, ...] = ()
    native: Literal["sat", "unsat", "unknown", "invalid"] = "invalid"
    product: Literal["CHECKED", "VIOLATIONS_FOUND", "UNABLE_TO_VERIFY", "INVALID_CANDIDATE"] = (
        "INVALID_CANDIDATE"
    )
    placements: tuple[TaskPlacement, ...] = ()
    blocks: tuple[ScheduleBlock, ...] = ()
    validation = None
    rule_results: tuple[FixedRuleResult, ...] = ()
    timeout_ms = (
        min(snapshot.policy.timeout_ms, max_timeout_ms)
        if max_timeout_ms is not None
        else snapshot.policy.timeout_ms
    )
    try:
        normalized, placements, blocks = admit_candidate(snapshot, proposal)
        assertions = _ground_rules(normalized, proposal, placements, blocks)
        covered = tuple(sorted(assertions))
        missing = set(required) - set(covered)
        if missing or not required or timeout_ms <= 0:
            native, product = "unknown", "UNABLE_TO_VERIFY"
            diagnostics = (
                _issue(
                    "unsupported_coverage",
                    "required rules have no supported fixed encoding",
                    *sorted(missing),
                ),
            )
        else:
            solver = z3.Solver()
            solver.set(timeout=timeout_ms, rlimit=snapshot.policy.resource_limit)
            labels: dict[str, str] = {}
            for index, rule_id in enumerate(required):
                label = f"required_rule_{index}"
                labels[label] = rule_id
                solver.assert_and_track(z3.And(*assertions[rule_id]), z3.Bool(label))
            status = solver.check()
            if status == z3.sat:
                native, product = "sat", "CHECKED"
                validation = independently_validate_candidate(
                    snapshot, proposal, normalized, placements, blocks
                )
            elif status == z3.unsat:
                native, product = "unsat", "VIOLATIONS_FOUND"
                core = tuple(sorted(labels[str(label)] for label in solver.unsat_core()))
                diagnostics = tuple(
                    _issue(
                        "fixed_rule_violation",
                        "the submitted candidate violates an admitted rule",
                        rule_id,
                    )
                    # These assertions are ground facts about one complete candidate.
                    # An unsat core is only one sufficient explanation, not the full
                    # repair scope. Keep the core separately and report every rule
                    # concretely false in this candidate, never unknown as false.
                    for rule_id in required
                    if z3.is_false(z3.simplify(z3.And(*assertions[rule_id])))
                )
            else:
                native, product = "unknown", "UNABLE_TO_VERIFY"
                diagnostics = (
                    _issue(
                        "checker_unknown",
                        "checker exhausted its time/resource budget or returned unknown",
                    ),
                )
        rule_results = tuple(
            FixedRuleResult(
                rule_id=rule_id,
                result=(
                    "unable"
                    if native in ("unknown", "invalid") or rule_id not in assertions
                    else "pass"
                    if z3.is_true(z3.simplify(z3.And(*assertions[rule_id])))
                    else "violation"
                    if z3.is_false(z3.simplify(z3.And(*assertions[rule_id])))
                    else "unable"
                ),
                category_key=_rule_categories(snapshot, rule_id)[0][0],
                category_title=_rule_categories(snapshot, rule_id)[1][0],
                category_keys=_rule_categories(snapshot, rule_id)[0],
                category_titles=_rule_categories(snapshot, rule_id)[1],
                encoding_version=FIXED_COMPILER_VERSION,
                candidate_values=_fixed_candidate_values(
                    normalized=normalized,
                    proposal=proposal,
                    rule_id=rule_id,
                    placements=placements,
                    blocks=blocks,
                ),
                technical_expression=(
                    z3.And(*assertions[rule_id]).sexpr() if rule_id in assertions else None
                ),
            )
            for rule_id in required
        )
    except CandidateAdmissionError as error:
        diagnostics = error.issues
    except ValueError as error:
        diagnostics = getattr(
            error, "issues", (_issue("invalid_snapshot", "snapshot or candidate admission failed"),)
        )
    except z3.Z3Exception:
        native, product = "unknown", "UNABLE_TO_VERIFY"
        diagnostics = (
            _issue("checker_infrastructure_failure", "fixed checker could not finish safely"),
        )
    if not rule_results:
        rule_results = tuple(
            FixedRuleResult(
                rule_id=rule_id,
                result="unable",
                category_key=_rule_categories(snapshot, rule_id)[0][0],
                category_title=_rule_categories(snapshot, rule_id)[1][0],
                category_keys=_rule_categories(snapshot, rule_id)[0],
                category_titles=_rule_categories(snapshot, rule_id)[1],
                encoding_version=FIXED_COMPILER_VERSION,
            )
            for rule_id in required
        )
    after = proposal.draft.semantic_digest
    if after != before or before != proposal.candidate_digest:
        product = "UNABLE_TO_VERIFY"
        diagnostics = (
            *diagnostics,
            _issue("candidate_digest_changed", "candidate changed while checking"),
        )
    check = FixedCheckReport(
        compiler_version=FIXED_COMPILER_VERSION,
        verifier_version=FIXED_VERIFIER_VERSION,
        solver_version=z3.get_version_string(),
        candidate_digest_before=before,
        candidate_digest_after=after,
        snapshot_digest=snapshot.snapshot_digest,
        native_status=native,
        product_status=product,
        required_rule_ids=required,
        covered_rule_ids=covered,
        unverified_required_rule_ids=tuple(sorted(set(required) - set(covered))),
        diagnostic_rule_ids=core,
        rule_results=rule_results,
        diagnostics=diagnostics,
        duration_ms=max(0, int((monotonic() - started) * 1000)),
        timeout_ms=max(1, timeout_ms),
        resource_limit=snapshot.policy.resource_limit,
    )
    return FixedCandidateResult(
        proposal=proposal, check=check, validation=validation, placements=placements, blocks=blocks
    )
