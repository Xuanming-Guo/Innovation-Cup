"""Regression coverage for bounded, evidence-complete fixed-candidate revisions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GeminiInvalidOutputError,
    GeminiTruncatedOutputError,
    ModelUsage,
    StructuredGatewayResponse,
)
from coordination.planning.authoring import (
    PLAN_PROMPT_VERSION,
    FixedCandidatePlanningService,
    _revision_tasks,
    build_authoring_input,
)
from coordination.planning.contracts import (
    DailyBudget,
    DependencyPayload,
    MovementPayload,
    PlanningSnapshot,
    ResourceCapacityPayload,
    canonical_digest,
)
from coordination.planning.fixed_contracts import (
    CompletePlanDraft,
    FixedCandidateResult,
    PlanProposalV2,
)
from coordination.planning.fixed_verifier import verify_fixed_candidate
from coordination.planning.northstar import (
    build_northstar_contract,
    build_northstar_proposal,
    build_northstar_snapshot,
    person_id,
    task_id,
)

COMPANY, RUN, REQUEST, CONTRACT = (UUID(int=index) for index in range(1, 5))
SOURCES = {f"LAUNCH-{index:02}": UUID(int=index + 10) for index in range(1, 8)}


@pytest.fixture
def snapshot() -> PlanningSnapshot:
    return build_northstar_snapshot(
        company_id=COMPANY,
        run_id=RUN,
        request_id=REQUEST,
        candidate_contract_id=CONTRACT,
        source_version_ids=SOURCES,
        source_manifest_digest="a" * 64,
        base_company_revision=7,
        frozen_at=datetime(2026, 9, 28, tzinfo=ZoneInfo("America/Los_Angeles")),
    )


def move_task(draft: CompletePlanDraft, key: str, minutes: int) -> CompletePlanDraft:
    shift = timedelta(minutes=minutes)
    return draft.model_copy(
        update={
            "tasks": tuple(
                task.model_copy(
                    update={
                        "start": task.start + shift,
                        "end": task.end + shift,
                        "blocks": tuple(
                            block.model_copy(
                                update={"start": block.start + shift, "end": block.end + shift}
                            )
                            for block in task.blocks
                        ),
                    }
                )
                if task.task_key == key
                else task
                for task in draft.tasks
            )
        }
    )


def failed_proposal(snapshot: PlanningSnapshot) -> PlanProposalV2:
    base = build_northstar_proposal(snapshot=snapshot, run_id=RUN, variant="D0")
    # Priya's Q1 crosses her protected Tuesday commitment. Alex's E1 also
    # crosses Monday's 12-13 unavailable break (the reported Live failure).
    draft = move_task(base.draft, "e1", -120)
    return base.model_copy(update={"draft": draft, "candidate_digest": draft.semantic_digest})


class MemoryLedger:
    def __init__(
        self,
        history: tuple[FixedCandidateResult, ...] = (),
        rounds: dict[int, str] | None = None,
    ) -> None:
        self.results = list(history)
        self.rounds = rounds or {}
        self.failures: list[str] = []
        self.started: list[dict[str, Any]] = []

    def history(self, **_: Any) -> tuple[FixedCandidateResult, ...]:
        return tuple(self.results)

    def admitted_context(self, **_: Any) -> dict[str, object]:
        return {
            **build_northstar_contract(
                company_id=COMPANY, request_id=REQUEST, source_version_ids=SOURCES
            ).model_dump(mode="json"),
            "existing_task_versions": {},
        }

    def model_round_states(self, **_: Any) -> dict[int, str]:
        return self.rounds

    def begin_model_run(self, **values: Any) -> None:
        self.started.append(values)

    def fail_model_run(self, **values: Any) -> None:
        self.failures.append(values["code"])

    def save_result(self, **values: Any) -> UUID | None:
        result: FixedCandidateResult = values["result"]
        self.results.append(result)
        return result.proposal.proposal_id if result.approvable else None


class Gateway:
    configuration = GatewayConfiguration(model="unit-only", retry_attempts=1)

    def __init__(self, responses: list[CompletePlanDraft | Exception]) -> None:
        self.responses = iter(responses)
        self.prompts: list[dict[str, Any]] = []

    def generate_structured(self, **values: Any) -> StructuredGatewayResponse:
        self.prompts.append(json.loads(values["prompt"]))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return StructuredGatewayResponse(
            payload=response,
            model_version="unit-only",
            provider_response_id=None,
            sdk_version="unit-only",
            finish_reason="STOP",
            usage=ModelUsage(prompt_tokens=1, candidate_tokens=1, total_tokens=2, thought_tokens=0),
        )


def run(
    snapshot: PlanningSnapshot,
    responses: list[CompletePlanDraft | Exception],
    *,
    ledger: MemoryLedger | None = None,
    attempt: int = 1,
) -> tuple[Any, MemoryLedger, Gateway]:
    ledger = ledger or MemoryLedger()
    gateway = Gateway(responses)
    context = CompanyContext(
        actor=AuthenticatedUser(
            user_id=uuid4(), role="authenticated", session_id=uuid4(), assurance_level="aal1"
        ),
        company_id=COMPANY,
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=RUN,
    )
    outcome = FixedCandidatePlanningService(
        gateway_factory=lambda _: gateway,
        ledger=ledger,
        max_input_characters=500_000,
    ).run(
        snapshot=snapshot,
        context=context,
        workflow_id=uuid4(),
        durable_attempt=attempt,
        checkpoint=lambda: None,
    )
    return outcome, ledger, gateway


def test_all_confirmed_violations_are_diagnosed_not_just_one_core(
    snapshot: PlanningSnapshot,
) -> None:
    candidate = failed_proposal(snapshot)
    before = candidate.model_dump_json()
    result = verify_fixed_candidate(snapshot, candidate)
    failed = {row.rule_id for row in result.check.rule_results if row.result == "violation"}
    diagnosed = {rule for issue in result.check.diagnostics for rule in issue.constraint_ids}
    assert {"protected.priya.tuesday", "resource.priya", "resource.alex"} <= failed
    assert diagnosed == failed
    assert set(result.check.diagnostic_rule_ids) < diagnosed  # Core is still separately retained.
    assert result.check.verifier_version == "alto-fixed-candidate-verifier.v3"
    assert candidate.model_dump_json() == before


def test_one_revision_can_fix_both_conflicts_with_concrete_feedback(
    snapshot: PlanningSnapshot,
) -> None:
    failed = failed_proposal(snapshot)
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    outcome, ledger, gateway = run(snapshot, [failed.draft, correct])
    assert outcome.status == "CHECKED" and outcome.plan_id is not None
    assert len(gateway.prompts) == len(ledger.results) == 2
    feedback = gateway.prompts[1]["repair_feedback"]
    assert {str(task_id(RUN, "e1")), str(task_id(RUN, "q1"))} <= set(feedback["revision_task_ids"])
    lunch = next(
        row
        for row in feedback["resource_conflicts"]["items"]
        if row["resource_id"] == str(person_id(COMPANY, "alex"))
        and row["code"] == "outside_availability"
    )
    assert lunch["task_ids"] == [str(task_id(RUN, "e1"))]
    assert lunch["offending_intervals"] == [
        {"start": "2026-09-28T19:00:00+00:00", "end": "2026-09-28T20:00:00+00:00"}
    ]
    protected = next(
        row
        for row in feedback["resource_conflicts"]["items"]
        if row["rule_id"] == "protected.priya.tuesday"
    )
    assert protected["code"] == "capacity_exceeded"
    assert protected["used_capacity_units_or_daily_slots"] == 2
    assert protected["admitted_limit"] == 1
    assert ledger.results[1].validation and ledger.results[1].validation.passed
    assert ledger.results[1].proposal.parent_proposal_id == ledger.results[0].proposal.proposal_id
    for recorded, prompt in zip(ledger.started, gateway.prompts, strict=True):
        assert recorded["input_digest"] == canonical_digest(prompt)
        assert recorded["configuration"]["prompt_version"] == PLAN_PROMPT_VERSION


def test_legacy_single_core_parent_still_uses_all_confirmed_rule_results(
    snapshot: PlanningSnapshot,
) -> None:
    parent = verify_fixed_candidate(snapshot, failed_proposal(snapshot))
    only_priya = tuple(
        issue
        for issue in parent.check.diagnostics
        if issue.constraint_ids == ("protected.priya.tuesday",)
    )
    legacy = parent.model_copy(
        update={"check": parent.check.model_copy(update={"diagnostics": only_priya})}
    )
    assert task_id(RUN, "e1") in _revision_tasks(snapshot, legacy)
    payload: Any = build_authoring_input(snapshot, legacy, 2)
    assert "resource.alex" in {
        rule
        for diagnostic in payload["actual_diagnostics"]
        for rule in diagnostic["constraint_ids"]
    }


def test_revision_cannot_move_unrelated_work(snapshot: PlanningSnapshot) -> None:
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    outcome, ledger, gateway = run(
        snapshot, [failed_proposal(snapshot).draft, move_task(correct, "m1", -30)]
    )
    assert outcome.reason == "revision_outside_violation_scope"
    assert len(gateway.prompts) == 2 and len(ledger.results) == 1
    assert str(task_id(RUN, "m1")) not in gateway.prompts[1]["repair_feedback"]["revision_task_ids"]


@pytest.mark.parametrize("kind", ["execution", "dependency"])
@pytest.mark.parametrize("forged_field", ["successor_task_id", "review_task_ids"])
def test_rejected_gate_cannot_grant_unrelated_task_repair_scope(
    snapshot: PlanningSnapshot, kind: str, forged_field: str
) -> None:
    if kind == "dependency":
        rules = tuple(
            rule.model_copy(
                update={
                    "payload": DependencyPayload(
                        family="dependency_lag",
                        predecessor_task_id=task_id(RUN, "e1"),
                        successor_task_id=task_id(RUN, "q1"),
                        minimum_lag_slots=0,
                        acceptance_required=False,
                    )
                }
            )
            if rule.constraint_id == "gate.e1.q1"
            else rule
            for rule in snapshot.constraints
        )
        snapshot = PlanningSnapshot.freeze(
            **{
                **snapshot.model_dump(exclude={"snapshot_digest", "constraints"}),
                "constraints": rules,
            }
        )
    base = build_northstar_proposal(snapshot=snapshot, run_id=RUN)
    unrelated = task_id(RUN, "m1")
    forged = base.draft.model_copy(
        update={
            "gates": tuple(
                gate.model_copy(
                    update={
                        forged_field: (unrelated,)
                        if forged_field == "review_task_ids"
                        else unrelated
                    }
                )
                if gate.rule_id == "gate.e1.q1"
                else gate
                for gate in base.draft.gates
            )
        }
    )
    parent = verify_fixed_candidate(
        snapshot,
        base.model_copy(update={"draft": forged, "candidate_digest": forged.semantic_digest}),
    )
    assert parent.check.product_status == "INVALID_CANDIDATE"
    assert any(
        issue.code in {"gate_authority_changed", "execution_gate_changed"}
        for issue in parent.check.diagnostics
    )
    affected = _revision_tasks(snapshot, parent)
    assert unrelated not in affected
    assert {task_id(RUN, key) for key in ("e1", "q1", "m2", "m3", "r1", "r2")} <= affected
    # Restoring the admitted gate is allowed; it cannot be used to smuggle an
    # otherwise-valid unrelated time change through a second response.
    outcome, ledger, gateway = run(snapshot, [forged, move_task(base.draft, "m1", -30)])
    assert outcome.reason == "revision_outside_violation_scope"
    assert len(ledger.results) == 1 and len(gateway.prompts) == 2
    restored, _, _ = run(snapshot, [forged, base.draft])
    assert restored.status == "CHECKED"


def test_admitted_review_link_expands_scope_without_candidate_gate(
    snapshot: PlanningSnapshot,
) -> None:
    # Reviews remain real admitted work even without a duplicate execution edge.
    rules = tuple(rule for rule in snapshot.constraints if rule.constraint_id != "gate.e1.q1")
    snapshot = PlanningSnapshot.freeze(
        **{**snapshot.model_dump(exclude={"snapshot_digest", "constraints"}), "constraints": rules}
    )
    base = build_northstar_proposal(snapshot=snapshot, run_id=RUN)
    without_gate = base.draft.model_copy(
        update={"gates": tuple(gate for gate in base.draft.gates if gate.rule_id != "gate.e1.q1")}
    )
    # Moving E1 later crosses the working-day boundary but doesn't make its
    # next-day review premature. Only the admitted ReviewPayload reaches Q1.
    failed = move_task(without_gate, "e1", 60)
    parent = verify_fixed_candidate(
        snapshot,
        base.model_copy(update={"draft": failed, "candidate_digest": failed.semantic_digest}),
    )
    assert parent.check.product_status == "VIOLATIONS_FOUND"
    affected = _revision_tasks(snapshot, parent)
    assert task_id(RUN, "q1") in affected and task_id(RUN, "m2") in affected
    assert task_id(RUN, "m1") not in affected


@pytest.mark.parametrize("move_reviewed_task", [False, True])
def test_review_owner_repair_can_only_refresh_reviewed_task_metadata(
    snapshot: PlanningSnapshot, move_reviewed_task: bool
) -> None:
    base = build_northstar_proposal(snapshot=snapshot, run_id=RUN)
    wrong_owner = person_id(COMPANY, "sam")
    wrong = base.draft.model_copy(
        update={
            "tasks": tuple(
                task.model_copy(
                    update={
                        "owner_resource_id": wrong_owner,
                        "blocks": tuple(
                            block.model_copy(update={"resource_id": wrong_owner})
                            for block in task.blocks
                        ),
                    }
                )
                if task.task_key == "q1"
                else task.model_copy(update={"reviewer_resource_ids": (wrong_owner,)})
                if task.task_key == "e1"
                else task
                for task in base.draft.tasks
            )
        }
    )
    parent = verify_fixed_candidate(
        snapshot,
        base.model_copy(update={"draft": wrong, "candidate_digest": wrong.semantic_digest}),
    )
    assert parent.check.product_status == "VIOLATIONS_FOUND"
    assert task_id(RUN, "q1") in _revision_tasks(snapshot, parent)
    assert task_id(RUN, "e1") not in _revision_tasks(snapshot, parent)
    replacement = move_task(base.draft, "e1", 15) if move_reviewed_task else base.draft
    outcome, ledger, gateway = run(snapshot, [wrong, replacement])
    assert len(gateway.prompts) == 2
    if move_reviewed_task:
        assert outcome.reason == "revision_outside_violation_scope" and len(ledger.results) == 1
    else:
        assert outcome.status == "CHECKED" and len(ledger.results) == 2
        reviewed_change = next(
            change
            for change in ledger.results[-1].proposal.changes
            if change.task_id == task_id(RUN, "e1")
        )
        assert reviewed_change.changed_fields == ("reviewer_resource_ids",)


def test_unknown_is_not_repairable_rule_feedback(snapshot: PlanningSnapshot) -> None:
    proposal = failed_proposal(snapshot)
    unknown = verify_fixed_candidate(snapshot, proposal, max_timeout_ms=0)
    assert unknown.check.product_status == "UNABLE_TO_VERIFY"
    assert all(row.result == "unable" for row in unknown.check.rule_results)
    assert _revision_tasks(snapshot, unknown) == set()
    payload = build_authoring_input(snapshot, unknown, 2)
    assert payload["repair_feedback"]["resource_conflicts"]["items"] == []  # type: ignore[index]
    outcome, _, gateway = run(snapshot, [], ledger=MemoryLedger((unknown,)))
    assert outcome.reason == "human_review_required" and not gateway.prompts


@pytest.mark.parametrize("error_type", [GeminiInvalidOutputError, GeminiTruncatedOutputError])
def test_failed_format_round_gets_safe_feedback_and_keeps_five_call_bound(
    snapshot: PlanningSnapshot, error_type: type[GeminiInvalidOutputError]
) -> None:
    outcome, ledger, gateway = run(snapshot, [error_type("secret raw output") for _ in range(5)])
    assert outcome.reason == "proposal_budget_exhausted" and outcome.plan_id is None
    assert len(gateway.prompts) == len(ledger.failures) == 5
    assert [prompt["remaining_proposals"] for prompt in gateway.prompts] == [5, 4, 3, 2, 1]
    for prompt in gateway.prompts[1:]:
        failure = prompt["repair_feedback"]["round_failure"]
        assert failure["code"] == error_type.code and failure["instruction"]
        assert "secret raw output" not in json.dumps(prompt)


def test_schema_feedback_does_not_fabricate_a_parent(snapshot: PlanningSnapshot) -> None:
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    error = GeminiInvalidOutputError("not copied to prompt")
    error.validation_issues = (("tasks[0].blocks[0].start", "datetime_parsing"),)
    outcome, ledger, gateway = run(snapshot, [error, correct])
    assert outcome.status == "CHECKED" and len(ledger.results) == 1
    prompt = gateway.prompts[1]
    assert prompt["parent_candidate"] is None and prompt["actual_diagnostics"] == []
    assert prompt["repair_feedback"]["round_failure"]["validation_issues"] == [
        {"path": "tasks[0].blocks[0].start", "category": "datetime_parsing"}
    ]


@pytest.mark.parametrize("field", ["purpose", "deliverable", "acceptance_criteria"])
def test_admitted_fact_rejection_points_to_exact_fields_not_rejected_prose(
    snapshot: PlanningSnapshot, field: str
) -> None:
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    wrong = correct.tasks[0].model_copy(
        update={
            field: ("untrusted replacement",)
            if field == "acceptance_criteria"
            else "untrusted replacement"
        }
    )
    malformed = correct.model_copy(update={"tasks": (wrong, *correct.tasks[1:])})
    outcome, ledger, gateway = run(snapshot, [malformed, correct])
    assert outcome.status == "CHECKED" and len(ledger.results) == 1
    failure = gateway.prompts[1]["repair_feedback"]["round_failure"]
    assert failure["code"] == "admitted_task_facts_changed"
    assert failure["fields_to_copy_from_admitted_contract"] == [
        {"task_key": correct.tasks[0].task_key, "fields": [field]}
    ]
    assert "untrusted replacement" not in json.dumps(gateway.prompts[1])


def test_prior_work_version_correction_uses_current_admitted_context(
    snapshot: PlanningSnapshot,
) -> None:
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    wrong = correct.model_copy(
        update={
            "tasks": (
                correct.tasks[0].model_copy(update={"expected_work_version": 999}),
                *correct.tasks[1:],
            )
        }
    )
    outcome, _, gateway = run(snapshot, [wrong, correct])
    assert outcome.status == "CHECKED"
    assert gateway.prompts[1]["repair_feedback"]["round_failure"]["code"] == (
        "prior_work_version_changed"
    )


def test_durable_resume_does_not_reset_failed_round_budget(snapshot: PlanningSnapshot) -> None:
    ledger = MemoryLedger(
        rounds={
            1: "model_invalid_output",
            2: "admitted_task_facts_changed",
            3: "model_invalid_output",
            4: "admitted_task_facts_changed",
        }
    )
    outcome, _, gateway = run(
        snapshot, [GeminiTruncatedOutputError("invalid")], ledger=ledger, attempt=2
    )
    assert outcome.reason == "proposal_budget_exhausted" and len(gateway.prompts) == 1
    assert gateway.prompts[0]["remaining_proposals"] == 1
    assert gateway.prompts[0]["repair_feedback"]["round_failure"]["code"] == (
        "admitted_task_facts_changed"
    )


def test_manager_recovery_can_continue_a_three_version_failed_chain(
    snapshot: PlanningSnapshot,
) -> None:
    first = failed_proposal(snapshot)
    history: list[FixedCandidateResult] = [verify_fixed_candidate(snapshot, first)]
    for version in (2, 3):
        parent = history[-1].proposal
        proposal = first.model_copy(
            update={
                "proposal_id": uuid4(),
                "version": version,
                "parent_proposal_id": parent.proposal_id,
            }
        )
        history.append(verify_fixed_candidate(snapshot, proposal))
    ledger = MemoryLedger(
        tuple(history), rounds={1: "succeeded", 2: "succeeded", 3: "succeeded"}
    )
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft

    outcome, stored, gateway = run(snapshot, [correct], ledger=ledger, attempt=2)

    assert outcome.status == "CHECKED" and outcome.plan_id is not None
    assert len(gateway.prompts) == 1
    assert gateway.prompts[0]["remaining_proposals"] == 2
    assert stored.results[-1].proposal.version == 4
    assert stored.results[-1].proposal.parent_proposal_id == history[-1].proposal.proposal_id


def test_allowed_revision_still_cannot_move_locked_work(snapshot: PlanningSnapshot) -> None:
    correct = build_northstar_proposal(snapshot=snapshot, run_id=RUN).draft
    e1 = next(task for task in correct.tasks if task.task_key == "e1")
    start = int((e1.start - snapshot.horizon_start).total_seconds() // (snapshot.slot_minutes * 60))
    end = int((e1.end - snapshot.horizon_start).total_seconds() // (snapshot.slot_minutes * 60))
    rules = tuple(
        rule.model_copy(
            update={
                "payload": MovementPayload(
                    family="movement",
                    task_id=e1.task_id,
                    movement="locked",
                    existing_resource_id=e1.owner_resource_id,
                    existing_slots=tuple(range(start, end)),
                )
            }
        )
        if rule.constraint_id == "movement.e1"
        else rule
        for rule in snapshot.constraints
    )
    locked = PlanningSnapshot.freeze(
        **{**snapshot.model_dump(exclude={"snapshot_digest", "constraints"}), "constraints": rules}
    )
    moved = move_task(correct, "e1", 15)
    # Even within a declared affected task's repair scope, the verifier rechecks
    # immutable movement permission. Scope is not authority to move a commitment.
    base = build_northstar_proposal(snapshot=locked, run_id=RUN)
    result = verify_fixed_candidate(
        locked, base.model_copy(update={"draft": moved, "candidate_digest": moved.semantic_digest})
    )
    assert not result.approvable
    assert any(
        row.rule_id == "movement.e1" and row.result == "violation"
        for row in result.check.rule_results
    )


def test_daily_budget_feedback_uses_admitted_local_day_and_consumption(
    snapshot: PlanningSnapshot,
) -> None:
    rules = tuple(
        rule.model_copy(
            update={
                "payload": rule.payload.model_copy(
                    update={"daily_budgets": (DailyBudget(day_index=0, max_active_slots=8),)}
                )
            }
        )
        if isinstance(rule.payload, ResourceCapacityPayload)
        and rule.payload.resource_id == person_id(COMPANY, "alex")
        else rule
        for rule in snapshot.constraints
    )
    bounded = PlanningSnapshot.freeze(
        **{**snapshot.model_dump(exclude={"snapshot_digest", "constraints"}), "constraints": rules}
    )
    result = verify_fixed_candidate(bounded, build_northstar_proposal(snapshot=bounded, run_id=RUN))
    assert result.check.product_status == "VIOLATIONS_FOUND"
    feedback: Any = build_authoring_input(bounded, result, 2)["repair_feedback"]
    row = next(
        row
        for row in feedback["resource_conflicts"]["items"]
        if row["code"] == "daily_budget_exceeded"
    )
    assert row["local_date"] == "2026-09-28" and row["timezone"] == "America/Los_Angeles"
    assert row["used_capacity_units_or_daily_slots"] == 12 and row["admitted_limit"] == 8
    assert row["task_ids"] == [str(task_id(RUN, "e1"))]
