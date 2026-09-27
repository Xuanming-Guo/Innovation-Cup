"""Versioned authored Northstar scenario, never attributed to a live model.

Both D0 and P1 use the production fixed verifier. These are application scenario
inputs, not precomputed pass flags or executable completion events.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from coordination.interpretation.contracts import (
    CandidateDependency,
    CandidateEstimate,
    CandidateTask,
    CandidateTaskContract,
    EvidenceBasis,
)
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GatewayResponse,
    GeminiInvalidOutputError,
    ModelUsage,
)
from coordination.interpretation.projection import InterpretationProjection
from coordination.planning.contracts import (
    ActiveParticipantsPayload,
    ConstraintPayload,
    DailyBudget,
    DeadlinePayload,
    EffortPayload,
    EligibilityPayload,
    ExecutionGatePayload,
    MovementPayload,
    PlanningPolicy,
    PlanningSnapshot,
    ReservationPayload,
    ResourceCapacityPayload,
    ReviewPayload,
    SegmentationPayload,
    TaskDefinitionPayload,
    TaskReviewPolicyPayload,
    ValidatedConstraint,
    WorkingWindowPayload,
)
from coordination.planning.fixed_contracts import (
    CompletePlanDraft,
    PlanProposalV2,
    ProposedBlock,
    ProposedGate,
    ProposedTask,
    proposal_changes,
)
from coordination.planning.fixed_verifier import FIXED_COMPILER_VERSION

NORTHSTAR_SCENARIO_VERSION: Literal["northstar-launch.2026-09.v1"] = "northstar-launch.2026-09.v1"
NORTHSTAR_TIMEZONE: Literal["America/Los_Angeles"] = "America/Los_Angeles"
NORTHSTAR_INTAKE = (
    "Prepare our analytics product for launch this Friday at 10 a.m. Coordinate Engineering, "
    "Design, QA, Marketing and Customer Support. Propose the remaining tasks, owners, reviews "
    "and handoffs. Respect existing commitments and working hours, "
    "and bring the plan to me for approval."
)
_ZONE = ZoneInfo(NORTHSTAR_TIMEZONE)
_ORIGIN = datetime(2026, 9, 28, tzinfo=_ZONE)

# key, day index, start, finish, owner, title, deliverable (the actual work remains human).
TASKS = (
    (
        "d1",
        0,
        "10:00",
        "12:00",
        "iris",
        "Finalise interface package",
        "Versioned interface package ready for Maya's review.",
    ),
    (
        "d2",
        0,
        "13:00",
        "13:30",
        "maya",
        "Accept interface criteria",
        "Accept or request revision of the exact D1 submission.",
    ),
    (
        "e1",
        0,
        "13:30",
        "16:30",
        "alex",
        "Integrate release candidate",
        "Versioned integration/release candidate against the accepted interface.",
    ),
    (
        "m1",
        0,
        "10:00",
        "12:00",
        "nora",
        "Draft provisional messaging",
        "Self-certified internal messaging draft; not publishing approval.",
    ),
    (
        "s1",
        0,
        "10:00",
        "12:00",
        "sam",
        "Outline provisional guide",
        "Self-certified internal guide outline; instructions remain unvalidated.",
    ),
    (
        "q1",
        1,
        "09:00",
        "11:00",
        "priya",
        "Validate integration candidate",
        "Accept or request revision of the exact E1 candidate.",
    ),
    (
        "m2",
        1,
        "13:00",
        "15:00",
        "iris",
        "Prepare final launch visuals",
        "Versioned visuals reflecting the accepted interface and tested build.",
    ),
    (
        "s2",
        1,
        "13:00",
        "15:00",
        "sam",
        "Write final customer guide",
        "Versioned guide matching validated workflow and the provisional outline.",
    ),
    (
        "m3",
        2,
        "09:00",
        "10:00",
        "nora",
        "Accept publishable message package",
        "Final messaging and acceptance of the exact visual/copy package.",
    ),
    (
        "s3",
        2,
        "10:00",
        "11:00",
        "priya",
        "Review customer guide",
        "Accept or request revision of the exact S2 guide against validated behavior.",
    ),
    (
        "e2",
        2,
        "13:00",
        "14:00",
        "alex",
        "Rehearse deployment and rollback",
        "Versioned staging deployment/rollback rehearsal evidence.",
    ),
    (
        "q2",
        2,
        "14:00",
        "14:30",
        "priya",
        "Accept readiness evidence",
        "Accept or request revision of the exact E2 readiness evidence.",
    ),
    (
        "r1",
        3,
        "09:00",
        "09:30",
        "maya",
        "Approve launch readiness",
        "Readiness approval only after all five required acceptance decisions.",
    ),
    (
        "l1",
        4,
        "10:00",
        "10:30",
        "alex",
        "Release and publish",
        "Release/publication evidence from Alex and active publisher Nora "
        "using authorised versions.",
    ),
    (
        "s4",
        4,
        "10:00",
        "11:00",
        "sam",
        "Provide launch support",
        "Submitted coverage record and customer-guide availability evidence.",
    ),
    (
        "q3",
        4,
        "10:30",
        "11:00",
        "priya",
        "Check post-release behavior",
        "Accept or request revision of exact L1 release evidence and deployed behavior.",
    ),
    (
        "r2",
        4,
        "11:00",
        "11:15",
        "maya",
        "Accept launch milestone",
        "Accept exact S4 evidence and the overall milestone after Q3 acceptance.",
    ),
)
REVIEWS = {"d1": "d2", "e1": "q1", "m2": "m3", "s2": "s3", "e2": "q2", "l1": "q3", "s4": "r2"}
GATES: tuple[
    tuple[str, str, Literal["submitted", "accepted", "approved", "self_certified"]], ...
] = (
    ("d1", "d2", "submitted"),
    ("d2", "e1", "accepted"),
    ("e1", "q1", "submitted"),
    ("d2", "m2", "accepted"),
    ("q1", "m2", "accepted"),
    ("m1", "m3", "self_certified"),
    ("m2", "m3", "submitted"),
    ("s1", "s2", "self_certified"),
    ("q1", "s2", "accepted"),
    ("s2", "s3", "submitted"),
    ("q1", "e2", "accepted"),
    ("e2", "q2", "submitted"),
    ("d2", "r1", "accepted"),
    ("q1", "r1", "accepted"),
    ("m3", "r1", "accepted"),
    ("s3", "r1", "accepted"),
    ("q2", "r1", "accepted"),
    ("r1", "l1", "approved"),
    ("r1", "s4", "approved"),
    ("l1", "q3", "submitted"),
    ("q3", "r2", "accepted"),
    ("s4", "r2", "submitted"),
)
_BY_KEY = {row[0]: row for row in TASKS}


class NorthstarInterpretationGateway:
    """Explicitly authored mode only; keeps normal evidence admission and ledgers."""

    configuration = GatewayConfiguration(
        model="authored:" + NORTHSTAR_SCENARIO_VERSION,
        prompt_version=NORTHSTAR_SCENARIO_VERSION,
        safety_profile="authored-no-network-no-tools.v1",
        timeout_seconds=1,
        retry_attempts=1,
    )

    def generate(self, projection: InterpretationProjection) -> GatewayResponse:
        if projection.original_request.strip() != NORTHSTAR_INTAKE:
            raise GeminiInvalidOutputError(
                "authored replay accepts only its versioned canonical intake"
            )
        sources = {
            excerpt.locator: source.source_version_id
            for source in projection.sources
            for excerpt in source.excerpts
            if source.freshness == "current"
        }
        if any(key not in sources for key in ("LAUNCH-02", "LAUNCH-07")):
            raise GeminiInvalidOutputError("the authorised Northstar source pack is incomplete")
        contract = build_northstar_contract(
            company_id=projection.company_id,
            request_id=projection.request_id,
            request_version=projection.request_version,
            source_version_ids=sources,
        )
        return GatewayResponse(
            contract=contract,
            model_version=self.configuration.model,
            provider_response_id=None,
            sdk_version="authored-no-sdk",
            finish_reason="AUTHORED",
            usage=ModelUsage(prompt_tokens=0, candidate_tokens=0, total_tokens=0, thought_tokens=0),
        )


def _at(day: int, clock: str) -> datetime:
    hour, minute = map(int, clock.split(":"))
    return _ORIGIN + timedelta(days=day, hours=hour, minutes=minute)


def _slot(instant: datetime) -> int:
    return int((instant - _ORIGIN).total_seconds() // 900)


def person_id(company_id: UUID, key: str) -> UUID:
    return uuid5(company_id, f"person:{key}")


def task_id(run_id: UUID, key: str) -> UUID:
    return uuid5(run_id, f"task:{key.lower()}")


def build_northstar_contract(
    *,
    company_id: UUID,
    request_id: UUID,
    source_version_ids: dict[str, UUID],
    request_version: int = 1,
) -> CandidateTaskContract:
    """The caller must persist this as an explicitly authored interpretation, not Gemini output."""
    source_id = source_version_ids["LAUNCH-02"]
    authority_id = source_version_ids["LAUNCH-07"]
    tasks = []
    for key, day, start, end, _owner, title, deliverable in TASKS:
        evidence = EvidenceBasis(
            kind="evidence", source_version_id=source_id, locator="LAUNCH-02", claim=deliverable
        )
        tasks.append(
            CandidateTask(
                task_key=key,
                title=title,
                purpose=(
                    "Prepare the already-developed analytics product "
                    "for the authorised Friday launch."
                ),
                deliverable=deliverable,
                acceptance_criteria=(
                    deliverable,
                    "Use only the exact authorised source and artifact versions.",
                ),
                timing_type="flexible_active",
                estimate=CandidateEstimate(
                    active_minutes=int((_at(day, end) - _at(day, start)).total_seconds() / 60),
                    lower_minutes=None,
                    upper_minutes=None,
                    bases=(evidence,),
                ),
                deadline=None,
                requirements=(),
                bases=(evidence,),
            )
        )
    dependencies = tuple(
        CandidateDependency(
            predecessor_task_key=pre,
            successor_task_key=post,
            dependency_type="finish_to_start",
            minimum_lag_minutes=0,
            bases=(
                EvidenceBasis(
                    kind="evidence",
                    source_version_id=authority_id,
                    locator="LAUNCH-07",
                    claim=(
                        f"{post.upper()} requires {pre.upper()} {state} "
                        "for the exact artifact version."
                    ),
                ),
            ),
        )
        for pre, post, state in GATES
    )
    # CandidateTaskContract v1 cannot express approved/self-certified states. Its
    # temporal edges are supplemented (not weakened) by the exact typed snapshot gates.
    return CandidateTaskContract(
        schema_version="candidate-task-contract.v1",
        company_id=company_id,
        request_id=request_id,
        request_version=request_version,
        tasks=tuple(tasks),
        dependencies=dependencies,
        assumptions=(),
        clarifications=(),
        unsupported=(),
    )


def build_northstar_snapshot(
    *,
    company_id: UUID,
    run_id: UUID,
    request_id: UUID,
    candidate_contract_id: UUID,
    source_version_ids: dict[str, UUID],
    source_manifest_digest: str,
    base_company_revision: int,
    frozen_at: datetime,
    permission_revision: str = "northstar-authority.v1",
    profile_revision: str = "northstar-profiles.v1",
) -> PlanningSnapshot:
    constraints: list[ValidatedConstraint] = []

    def add(key: str, payload: ConstraintPayload, source: str) -> None:
        constraints.append(
            ValidatedConstraint(
                constraint_id=key,
                company_id=company_id,
                strength="hard",
                payload=payload,
                source_version_ids=(source_version_ids[source],),
                authority_refs=(NORTHSTAR_SCENARIO_VERSION,),
                confidentiality="company",
                negotiability="locked",
                confirmation="confirmed",
            )
        )

    available = tuple(
        slot
        for day in range(5)
        for start, end in (("09:00", "12:00"), ("13:00", "17:00"))
        for slot in range(_slot(_at(day, start)), _slot(_at(day, end)))
    )
    for key in ("alex", "iris", "maya", "nora", "priya", "sam"):
        add(
            f"resource.{key}",
            ResourceCapacityPayload(
                family="resource_capacity",
                resource_id=person_id(company_id, key),
                resource_kind="human",
                timezone=NORTHSTAR_TIMEZONE,
                available_slots=available,
                capacity_per_slot=1,
                daily_budgets=tuple(
                    DailyBudget(day_index=day, max_active_slots=28) for day in range(5)
                ),
                capability_keys=(f"northstar.{key}",),
                permission_keys=("northstar.launch",),
            ),
            "LAUNCH-04",
        )
    add(
        "protected.priya.tuesday",
        ReservationPayload(
            family="reservation",
            resource_id=person_id(company_id, "priya"),
            reservation_ref="northstar:priya:2026-09-29:11-12",
            slots=tuple(range(_slot(_at(1, "11:00")), _slot(_at(1, "12:00")))),
            capacity_units=1,
            consumes_daily_budget=True,
        ),
        "LAUNCH-04",
    )
    review_keys = {*REVIEWS.values(), "r1"}
    for key, day, start, end, owner, title, _deliverable in TASKS:
        task = task_id(run_id, key)
        effort = _slot(_at(day, end)) - _slot(_at(day, start))
        add(
            f"task.{key}",
            TaskDefinitionPayload(
                family="task_definition",
                task_id=task,
                task_key=key,
                title=title,
                scheduling_kind="review" if key in review_keys else "flexible_active",
            ),
            "LAUNCH-02",
        )
        add(
            f"effort.{key}",
            EffortPayload(family="effort", task_id=task, active_slots=effort, elapsed_slots=effort),
            "LAUNCH-02",
        )
        add(
            f"eligibility.{key}",
            EligibilityPayload(
                family="eligibility",
                task_id=task,
                allowed_resource_ids=(person_id(company_id, owner),),
            ),
            "LAUNCH-05",
        )
        add(
            f"window.{key}",
            WorkingWindowPayload(
                family="working_window",
                task_id=task,
                release_slot=_slot(_at(day, "10:00" if key == "l1" else "09:00")),
                end_slot=_slot(_at(day, "10:30" if key == "l1" else "17:00")),
            ),
            "LAUNCH-04",
        )
        add(
            f"movement.{key}",
            MovementPayload(family="movement", task_id=task, movement="new", existing_slots=()),
            "LAUNCH-07",
        )
        add(
            f"segments.{key}",
            SegmentationPayload(
                family="segmentation",
                task_id=task,
                split_allowed=False,
                minimum_segment_slots=effort,
                max_segments_per_day=1,
            ),
            "LAUNCH-04",
        )
        policy: Literal["exact_review", "self_certifiable_internal_draft", "not_required"] = (
            "exact_review"
            if key in REVIEWS
            else "self_certifiable_internal_draft"
            if key in ("m1", "s1")
            else "not_required"
        )
        add(
            f"review-policy.{key}",
            TaskReviewPolicyPayload(
                family="task_review_policy",
                task_id=task,
                policy=policy,
                review_task_ids=(task_id(run_id, REVIEWS[key]),) if key in REVIEWS else (),
            ),
            "LAUNCH-07",
        )
        if key in REVIEWS:
            add(
                f"review.{key}",
                ReviewPayload(
                    family="acceptance_review",
                    reviewed_task_id=task,
                    review_task_id=task_id(run_id, REVIEWS[key]),
                    require_separate_resource=True,
                ),
                "LAUNCH-07",
            )
    add(
        "participants.l1",
        ActiveParticipantsPayload(
            family="active_participants",
            task_id=task_id(run_id, "l1"),
            participant_resource_ids=(person_id(company_id, "nora"),),
        ),
        "LAUNCH-07",
    )
    # The release starts at 10:00, while accepted completion belongs to R2 at 11:15.
    add(
        "deadline.r2",
        DeadlinePayload(
            family="deadline",
            task_id=task_id(run_id, "r2"),
            requested_finish_slot=_slot(_at(4, "11:15")),
            hard_finish_slot=_slot(_at(4, "11:15")),
        ),
        "LAUNCH-02",
    )
    for pre, post, state in GATES:
        add(
            f"gate.{pre}.{post}",
            ExecutionGatePayload(
                family="execution_gate",
                predecessor_task_id=task_id(run_id, pre),
                successor_task_id=task_id(run_id, post),
                required_state=state,
                minimum_lag_slots=0,
            ),
            "LAUNCH-07",
        )
    return PlanningSnapshot.freeze(
        snapshot_id=uuid5(request_id, NORTHSTAR_SCENARIO_VERSION),
        company_id=company_id,
        request_id=request_id,
        candidate_contract_id=candidate_contract_id,
        base_company_revision=base_company_revision,
        horizon_start=_ORIGIN,
        horizon_end=_at(4, "17:00"),
        slot_minutes=15,
        source_manifest_digest=source_manifest_digest,
        permission_revision=permission_revision,
        profile_revision=profile_revision,
        estimate_revision=NORTHSTAR_SCENARIO_VERSION,
        compiler_version=FIXED_COMPILER_VERSION,
        policy=PlanningPolicy(
            policy_version=NORTHSTAR_SCENARIO_VERSION,
            timeout_ms=10_000,
            resource_limit=1_000_000,
            allow_authorized_repair=False,
            max_repair_attempts=0,
        ),
        constraints=tuple(constraints),
        frozen_at=frozen_at,
    )


def build_northstar_proposal(
    *,
    snapshot: PlanningSnapshot,
    run_id: UUID,
    variant: Literal["D0", "P1"] = "P1",
    parent: PlanProposalV2 | None = None,
    author_kind: Literal["authored_replay", "authored_check"] = "authored_replay",
) -> PlanProposalV2:
    """P1 is authored reference data. Passing verification never changes it."""
    tasks = []
    for key, day, start, end, owner, title, deliverable in TASKS:
        if variant == "D0" and key == "q1":
            start, end = "10:00", "12:00"
        task = task_id(run_id, key)
        start_at, end_at = _at(day, start), _at(day, end)
        owner_id = person_id(snapshot.company_id, owner)
        blocks = [
            ProposedBlock(
                resource_id=owner_id, role="owner", capacity_units=1, start=start_at, end=end_at
            )
        ]
        if key == "l1":
            blocks.append(
                ProposedBlock(
                    resource_id=person_id(snapshot.company_id, "nora"),
                    role="participant",
                    capacity_units=1,
                    start=start_at,
                    end=end_at,
                )
            )
        reviewer_ids = (
            (person_id(snapshot.company_id, _BY_KEY[REVIEWS[key]][4]),) if key in REVIEWS else ()
        )
        tasks.append(
            ProposedTask(
                task_id=task,
                task_key=key,
                title=title,
                purpose=(
                    "Prepare the already-developed analytics product "
                    "for the authorised Friday launch."
                ),
                deliverable=deliverable,
                acceptance_criteria=(
                    deliverable,
                    "Use only the exact authorised source and artifact versions.",
                ),
                scheduling_kind="review" if key in {*REVIEWS.values(), "r1"} else "flexible_active",
                owner_resource_id=owner_id,
                effort_minutes=int((end_at - start_at).total_seconds() / 60),
                start=start_at,
                end=end_at,
                blocks=tuple(blocks),
                review_policy="exact_review"
                if key in REVIEWS
                else "self_certifiable_internal_draft"
                if key in ("m1", "s1")
                else "not_required",
                reviewer_resource_ids=reviewer_ids,
                confidentiality="company",
                evidence_rule_ids=tuple(
                    rule.constraint_id
                    for rule in snapshot.constraints
                    if getattr(rule.payload, "task_id", None) == task
                ),
                audience_resource_ids=tuple(sorted({owner_id, *reviewer_ids}, key=str)),
            )
        )
    gates = tuple(
        ProposedGate(
            rule_id=f"gate.{pre}.{post}",
            predecessor_task_id=task_id(run_id, pre),
            successor_task_id=task_id(run_id, post),
            required_state=state,
            artifact_version_policy="exact_submitted_version",
            review_task_ids=(),
            minimum_lag_minutes=0,
        )
        for pre, post, state in GATES
    )
    draft = CompletePlanDraft(
        timezone=NORTHSTAR_TIMEZONE,
        tasks=tuple(tasks),
        gates=gates,
        assumptions=(),
        unresolved_items=(),
    )
    version = parent.version + 1 if parent else 1
    return PlanProposalV2(
        proposal_id=uuid5(snapshot.snapshot_id, f"authored:{variant}:{version}"),
        company_id=snapshot.company_id,
        demo_run_id=run_id,
        request_id=snapshot.request_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_digest=snapshot.snapshot_digest,
        source_manifest_digest=snapshot.source_manifest_digest,
        version=version,
        parent_proposal_id=parent.proposal_id if parent else None,
        author_kind=author_kind,
        draft=draft,
        candidate_digest=draft.semantic_digest,
        changes=proposal_changes(parent, draft),
    )
