from __future__ import annotations

import json
import runpy
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GeminiInvalidOutputError,
    ModelUsage,
    StructuredGatewayResponse,
)
from coordination.planning.authoring import FixedCandidatePlanningService, build_authoring_input
from coordination.planning.contracts import (
    PlanningSnapshot,
    ReservationPayload,
    WorkingWindowPayload,
)
from coordination.planning.fixed_contracts import (
    MAX_FIXED_PLAN_PROPOSALS,
    CompletePlanDraft,
    PlanProposalV2,
)
from coordination.planning.fixed_verifier import verify_fixed_candidate
from coordination.planning.materializer import (
    AvailabilityWindow,
    MaterializationError,
    PlanningResourceProfile,
)
from coordination.planning.northstar import (
    build_northstar_contract,
    build_northstar_proposal,
    build_northstar_snapshot,
    person_id,
)
from coordination.planning.northstar_authority import (
    build_live_northstar_snapshot,
    canonical_authority_manifest,
)
from coordination.workspace.contracts import Project
from coordination.workspace.graph_read import graph

COMPANY = UUID("11111111-0000-4111-8111-111111111111")
RUN = UUID("22222222-0000-4222-8222-222222222222")
REQUEST = UUID("33333333-0000-4333-8333-333333333333")
CONTRACT = UUID("44444444-0000-4444-8444-444444444444")
SOURCES = {f"LAUNCH-{index:02}": UUID(int=index) for index in range(1, 8)}
ZONE = ZoneInfo("America/Los_Angeles")
START = datetime(2026, 9, 28, tzinfo=ZONE)


def snapshot() -> PlanningSnapshot:
    return build_northstar_snapshot(
        company_id=COMPANY,
        run_id=RUN,
        request_id=REQUEST,
        candidate_contract_id=CONTRACT,
        source_version_ids=SOURCES,
        source_manifest_digest="a" * 64,
        base_company_revision=7,
        frozen_at=START,
    )


def proposal(draft: CompletePlanDraft, base: PlanProposalV2) -> PlanProposalV2:
    return PlanProposalV2.model_validate(
        {
            **base.model_dump(mode="json"),
            "draft": draft.model_dump(mode="json"),
            "candidate_digest": draft.semantic_digest,
        }
    )


def test_reference_p1_passes_both_checks_without_candidate_mutation() -> None:
    frozen = snapshot()
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN)
    before = p1.model_dump_json()
    result = verify_fixed_candidate(frozen, p1)
    assert result.approvable, result.model_dump_json()
    assert result.check.native_status == "sat"
    assert result.validation and result.validation.passed
    assert set(result.check.required_rule_ids) <= set(result.check.covered_rule_ids)
    assert len(result.check.rule_results) == len(result.check.required_rule_ids)
    assert p1.model_dump_json() == before
    assert len(result.placements) == 17 and len(result.blocks) == 18

    protected = next(
        row for row in result.check.rule_results if row.rule_id == "protected.priya.tuesday"
    )
    assert protected.result == "pass"
    assert protected.category_keys == ("protected_time",)
    assert protected.encoding_version == "alto-fixed-candidate-compiler.v1"
    assert protected.technical_expression
    assert protected.technical_expression.startswith("(and ")
    assert protected.candidate_values["resource_label"] == "Priya"
    assert protected.candidate_values["overlap"] is False
    protected_interval = protected.candidate_values["protected_interval"]
    assert protected_interval["start_at"].endswith("T11:00:00-07:00")
    assert protected_interval["end_at"].endswith("T12:00:00-07:00")
    assert protected_interval["interval_semantics"] == "half-open"
    q1 = next(
        item
        for item in protected.candidate_values["candidate_intervals"]
        if item["task_key"] == "Q1"
    )
    assert q1["start_at"].endswith("T09:00:00-07:00")
    assert q1["end_at"].endswith("T11:00:00-07:00")
    assert q1["interval_semantics"] == "half-open"


def test_d0_records_real_protected_capacity_violation_without_repair() -> None:
    frozen = snapshot()
    d0 = build_northstar_proposal(
        snapshot=frozen, run_id=RUN, variant="D0", author_kind="authored_check"
    )
    result = verify_fixed_candidate(frozen, d0)
    assert result.check.product_status == "VIOLATIONS_FOUND"
    assert result.check.native_status == "unsat" and not result.approvable
    failed = {row.rule_id for row in result.check.rule_results if row.result == "violation"}
    assert "protected.priya.tuesday" in failed
    q1 = next(task for task in result.proposal.draft.tasks if task.task_key == "q1")
    assert q1.start.hour == 10 and q1.end.hour == 12
    protected = next(
        row for row in result.check.rule_results if row.rule_id == "protected.priya.tuesday"
    )
    assert protected.technical_expression
    assert protected.candidate_values["overlap"] is True
    assert protected.rule_id in result.check.diagnostic_rule_ids


def test_every_active_participant_consumes_the_full_interval() -> None:
    frozen = snapshot()
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN)
    tasks = tuple(
        task.model_copy(
            update={"blocks": tuple(block for block in task.blocks if block.role != "participant")}
        )
        if task.task_key == "l1"
        else task
        for task in p1.draft.tasks
    )
    result = verify_fixed_candidate(
        frozen, proposal(p1.draft.model_copy(update={"tasks": tasks}), p1)
    )
    assert not result.approvable
    assert any(
        row.rule_id == "participants.l1" and row.result == "violation"
        for row in result.check.rule_results
    )


def test_removed_gate_or_invented_person_is_invalid_not_a_smaller_checked_model() -> None:
    frozen = snapshot()
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN)
    draft = p1.draft.model_copy(update={"gates": p1.draft.gates[:-1]})
    result = verify_fixed_candidate(frozen, proposal(draft, p1))
    assert result.check.product_status == "INVALID_CANDIDATE"
    assert all(row.result == "unable" for row in result.check.rule_results)
    task = p1.draft.tasks[0].model_copy(update={"owner_resource_id": uuid4()})
    result = verify_fixed_candidate(
        frozen, proposal(p1.draft.model_copy(update={"tasks": (task, *p1.draft.tasks[1:])}), p1)
    )
    assert result.check.product_status == "INVALID_CANDIDATE"


def test_exact_time_is_never_rounded_and_timeout_is_not_a_violation() -> None:
    frozen = snapshot()
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN)
    task = p1.draft.tasks[0].model_copy(
        update={"start": p1.draft.tasks[0].start + timedelta(minutes=1)}
    )
    result = verify_fixed_candidate(
        frozen, proposal(p1.draft.model_copy(update={"tasks": (task, *p1.draft.tasks[1:])}), p1)
    )
    assert result.check.product_status == "INVALID_CANDIDATE"
    exhausted = verify_fixed_candidate(frozen, p1, max_timeout_ms=0)
    assert exhausted.check.product_status == "UNABLE_TO_VERIFY"
    assert exhausted.check.native_status == "unknown"
    assert not exhausted.approvable


def live_values() -> dict[str, Any]:
    windows = tuple(
        AvailabilityWindow(
            start_at=START + timedelta(days=day, hours=start),
            end_at=START + timedelta(days=day, hours=end),
        )
        for day in range(5)
        for start, end in ((9, 12), (13, 17))
    )
    profiles = tuple(
        PlanningResourceProfile(
            resource_id=person_id(COMPANY, key),
            timezone=str(ZONE),
            availability=windows,
            capability_keys=("northstar." + key,),
            permission_keys=("northstar.launch",),
            daily_active_minutes=420,
            profile_revision=1,
            estimate_revision=1,
        )
        for key in ("alex", "iris", "maya", "nora", "priya", "sam")
    )
    return dict(
        company_id=COMPANY,
        run_id=RUN,
        request_id=REQUEST,
        candidate_contract_id=CONTRACT,
        contract=build_northstar_contract(
            company_id=COMPANY, request_id=REQUEST, source_version_ids=SOURCES
        ),
        source_version_ids=SOURCES,
        authority=canonical_authority_manifest(),
        source_manifest_digest="a" * 64,
        base_company_revision=7,
        frozen_at=START,
        profiles=profiles,
        busy_intervals=(
            (
                person_id(COMPANY, "priya"),
                START + timedelta(days=1, hours=11),
                START + timedelta(days=1, hours=12),
                "calendar:protected",
            ),
        ),
    )


def test_live_admission_retains_every_authority_family_but_not_p1_task_days() -> None:
    live = build_live_northstar_snapshot(**live_values())
    families = [rule.payload.family for rule in live.constraints]
    assert families.count("execution_gate") == 22
    assert families.count("task_review_policy") == 17
    assert families.count("active_participants") == 1
    assert families.count("acceptance_review") == 7
    q1_window = next(rule.payload for rule in live.constraints if rule.constraint_id == "window.q1")
    assert isinstance(q1_window, WorkingWindowPayload)
    assert q1_window.release_slot == 0 and q1_window.end_slot == live.slot_count
    p1 = build_northstar_proposal(snapshot=live, run_id=RUN)
    assert verify_fixed_candidate(live, p1).approvable


def test_live_reservation_ids_ignore_irrelevant_busy_rows_and_input_order() -> None:
    values = live_values()
    protected = values["busy_intervals"][0]
    irrelevant = (
        UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        START + timedelta(hours=15),
        START + timedelta(hours=16),
        "calendar:background",
    )
    values["busy_intervals"] = (irrelevant, protected)
    first = build_live_northstar_snapshot(**values)
    values["busy_intervals"] = (protected, irrelevant)
    second = build_live_northstar_snapshot(**values)

    assert first.snapshot_digest == second.snapshot_digest
    reservations = [
        rule.constraint_id
        for rule in first.constraints
        if isinstance(rule.payload, ReservationPayload)
    ]
    assert reservations == ["live.reservation.0"]


@pytest.mark.parametrize("missing", ["task", "gate", "protected", "authority"])
def test_live_admission_fails_closed_on_incomplete_or_changed_authority(missing: str) -> None:
    values = live_values()
    if missing == "task":
        values["contract"] = values["contract"].model_copy(
            update={"tasks": values["contract"].tasks[:-1]}
        )
    elif missing == "gate":
        values["contract"] = values["contract"].model_copy(
            update={"dependencies": values["contract"].dependencies[:-1]}
        )
    elif missing == "protected":
        values["busy_intervals"] = ()
    else:
        first = values["authority"].tasks[0].model_copy(update={"active_minutes": 15})
        values["authority"] = values["authority"].model_copy(
            update={"tasks": (first, *values["authority"].tasks[1:])}
        )
    with pytest.raises(MaterializationError):
        build_live_northstar_snapshot(**values)


class MemoryLedger:
    def __init__(self) -> None:
        self.results: list[Any] = []
        self.failures: list[str] = []
        self.started: list[dict[str, Any]] = []

    def history(self, **_: Any) -> tuple[Any, ...]:
        return tuple(self.results)

    def admitted_context(self, **_: Any) -> dict[str, Any]:
        return {
            **build_northstar_contract(
                company_id=COMPANY, request_id=REQUEST, source_version_ids=SOURCES
            ).model_dump(mode="json"),
            "existing_task_versions": {},
        }

    def model_round_states(self, **_: Any) -> dict[int, str]:
        return {}

    def begin_model_run(self, **values: Any) -> None:
        self.started.append(values)

    def fail_model_run(self, **values: Any) -> None:
        self.failures.append(values["code"])

    def save_result(self, **values: Any) -> UUID | None:
        self.results.append(values["result"])
        return values["result"].proposal.proposal_id if values["result"].approvable else None


class FakeGateway:
    configuration = GatewayConfiguration(model="unit-only", retry_attempts=1)

    def __init__(self, drafts: list[CompletePlanDraft | Exception]) -> None:
        self.drafts = iter(drafts)
        self.calls = 0

    def generate_structured(self, **_: Any) -> StructuredGatewayResponse:
        self.calls += 1
        draft = next(self.drafts)
        if isinstance(draft, Exception):
            raise draft
        return StructuredGatewayResponse(
            payload=draft,
            model_version="unit-only",
            provider_response_id=None,
            sdk_version="unit-only",
            finish_reason="STOP",
            usage=ModelUsage(prompt_tokens=1, candidate_tokens=1, total_tokens=2, thought_tokens=0),
        )


def run_authoring(
    drafts: list[CompletePlanDraft | Exception],
    *,
    max_proposals: int = MAX_FIXED_PLAN_PROPOSALS,
) -> tuple[Any, MemoryLedger, FakeGateway]:
    ledger = MemoryLedger()
    gateway = FakeGateway(drafts)
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
    service = FixedCandidatePlanningService(
        gateway_factory=lambda _: gateway,
        ledger=ledger,
        max_input_characters=500000,
        max_proposals=max_proposals,
    )
    return (
        service.run(
            snapshot=snapshot(),
            context=context,
            workflow_id=uuid4(),
            durable_attempt=1,
            checkpoint=lambda: None,
        ),
        ledger,
        gateway,
    )


def test_actual_failed_parent_can_be_revised_once_then_independently_checked() -> None:
    frozen = snapshot()
    d0 = build_northstar_proposal(snapshot=frozen, run_id=RUN, variant="D0").draft
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN).draft
    outcome, ledger, gateway = run_authoring([d0, p1])
    assert outcome.status == "CHECKED" and outcome.plan_id
    assert gateway.calls == 2 and len(ledger.results) == 2
    assert ledger.results[1].proposal.parent_proposal_id == ledger.results[0].proposal.proposal_id
    assert ledger.results[1].proposal.author_kind == "ai_authored"


def test_locked_demo_budget_stops_after_one_gemini_candidate() -> None:
    frozen = snapshot()
    d0 = build_northstar_proposal(snapshot=frozen, run_id=RUN, variant="D0").draft
    p1 = build_northstar_proposal(snapshot=frozen, run_id=RUN).draft
    outcome, ledger, gateway = run_authoring([d0, p1], max_proposals=1)
    assert outcome.status == "VIOLATIONS_FOUND"
    assert outcome.reason == "proposal_budget_exhausted"
    assert outcome.model_rounds == 1
    assert gateway.calls == 1
    assert len(ledger.results) == 1


def test_provider_capacity_wait_finishes_before_model_evidence_and_sdk_call() -> None:
    events: list[str] = []
    ledger = MemoryLedger()
    original_begin = ledger.begin_model_run

    def begin_model_run(**values: Any) -> None:
        events.append("model-run")
        original_begin(**values)

    ledger.begin_model_run = begin_model_run  # type: ignore[method-assign]
    base_gateway = FakeGateway([build_northstar_proposal(snapshot=snapshot(), run_id=RUN).draft])

    class OrderedGateway:
        configuration = base_gateway.configuration

        def generate_structured(self, **values: Any) -> StructuredGatewayResponse:
            events.append("sdk")
            return base_gateway.generate_structured(**values)

    selected = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=COMPANY,
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=RUN,
    )
    service = FixedCandidatePlanningService(
        gateway_factory=lambda _: OrderedGateway(),
        ledger=ledger,
        max_input_characters=500000,
        before_model_run=lambda: events.append("capacity"),
    )

    result = service.run(
        snapshot=snapshot(),
        context=selected,
        workflow_id=uuid4(),
        durable_attempt=1,
        checkpoint=lambda: None,
    )

    assert result.status == "CHECKED"
    assert events[:3] == ["capacity", "model-run", "sdk"]


def test_unchanged_candidate_and_invalid_schema_cannot_loop() -> None:
    draft = build_northstar_proposal(snapshot=snapshot(), run_id=RUN, variant="D0").draft
    outcome, ledger, gateway = run_authoring([draft, draft])
    assert outcome.reason == "unchanged_candidate_not_retried"
    assert gateway.calls == 2 and len(ledger.results) == 1
    outcome, ledger, gateway = run_authoring([GeminiInvalidOutputError("bad") for _ in range(5)])
    assert gateway.calls == 5 and len(ledger.failures) == 5
    assert outcome.status == "INVALID_CANDIDATE" and outcome.plan_id is None


def test_operator_manifest_is_bounded_and_preferences_are_director_scoped() -> None:
    module = runpy.run_path(
        str(Path(__file__).resolve().parents[3] / "supabase/scripts/alto_scenario.py")
    )
    manifest = module["manifest"]()
    sources = {source["key"]: source for source in manifest["sources"]}
    assert len(sources) == 7
    assert all(len(source["text"]) <= 12000 for source in sources.values())
    assert sources["LAUNCH-07"]["planning_authority"] == canonical_authority_manifest().model_dump(
        mode="json"
    )
    assert set(sources["LAUNCH-06"]["audience_employee_ids"]) == {
        str(module["record_id"]("person:maya")),
        str(module["record_id"]("person:jordan")),
    }
    assert "P1" not in sources["LAUNCH-04"]["text"]
    frozen = snapshot()
    d0 = verify_fixed_candidate(
        frozen, build_northstar_proposal(snapshot=frozen, run_id=RUN, variant="D0")
    )
    contract = build_northstar_contract(
        company_id=COMPANY, request_id=REQUEST, source_version_ids=SOURCES
    )
    payload = build_authoring_input(frozen, d0, 2, contract.model_dump(mode="json"))
    assert (
        len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        <= 150000
    )


class Rows:
    def __init__(self, values: list[dict[str, Any]]) -> None:
        self.values = values

    def fetchall(self) -> list[dict[str, Any]]:
        return self.values

    def fetchone(self) -> dict[str, Any] | None:
        return self.values[0] if self.values else None


def test_history_preview_uses_exact_d0_evidence_and_preserves_default_committed_graph() -> None:
    frozen = snapshot()
    d0 = build_northstar_proposal(
        snapshot=frozen, run_id=RUN, variant="D0", author_kind="authored_check"
    )
    p1 = build_northstar_proposal(
        snapshot=frozen, run_id=RUN, parent=d0, author_kind="authored_check"
    )
    versions = {item.proposal_id: item for item in (d0, p1)}
    project_id = uuid4()
    checked_ids: list[UUID] = []

    class Connection:
        def execute(self, sql: str, params: tuple[Any, ...]) -> Rows:
            if "from app.work_items w" in sql:
                return Rows(
                    [
                        {
                            "id": p1.draft.tasks[0].task_id,
                            "task_key": "D1",
                            "title": "Committed title",
                            "team": "design",
                            "owner_name": "Iris",
                            "owner_employee_id": person_id(COMPANY, "iris"),
                            "status": "accepted",
                            "start_at": START,
                            "finish_at": START + timedelta(hours=1),
                            "reviewer_name": "Maya",
                            "summary": "Committed work remains authoritative.",
                            "row_version": 3,
                            "source_plan_id": p1.proposal_id,
                            "is_mine": False,
                            "can_work": False,
                        }
                    ]
                )
            if "proposal.id as proposal_id" in sql:
                return Rows(
                    [
                        {
                            "proposal_id": item.proposal_id,
                            "version": item.version,
                            "author_kind": item.author_kind,
                            "product_status": "CHECKED" if item is p1 else "VIOLATIONS_FOUND",
                            "independent_validation_passed": item is p1,
                            "candidate_digest": item.candidate_digest,
                            "created_at": START + timedelta(seconds=item.version),
                        }
                        for item in (p1, d0)
                    ]
                )
            if "proposal.candidate_payload" in sql:
                selected = versions[params[2]] if params[2] else p1
                return Rows(
                    [
                        {
                            "id": selected.proposal_id,
                            "candidate_payload": {"proposal": selected.model_dump(mode="json")},
                            "candidate_digest": bytes.fromhex(selected.candidate_digest),
                            "plan_id": p1.proposal_id if selected is p1 else None,
                            "verification_id": selected.proposal_id,
                            "product_status": "CHECKED" if selected is p1 else "VIOLATIONS_FOUND",
                            "passed": selected is p1,
                            "snapshot_id": frozen.snapshot_id,
                            "commitment_id": None,
                        }
                    ]
                )
            if "from app.plan_commitments c" in sql:
                return Rows([{"plan_id": p1.proposal_id}])
            if "from app.task_dependency_edges" in sql:
                return Rows([])
            if "from app.execution_resources r join" in sql:
                return Rows(
                    [
                        {
                            "id": person_id(COMPANY, key),
                            "employee_id": person_id(COMPANY, key),
                            "display_name": key.title(),
                            "function_key": "engineering",
                        }
                        for key in ("alex", "iris", "maya", "nora", "priya", "sam")
                    ]
                )
            if "from app.plan_verification_rule_results result" in sql:
                checked_ids.append(params[1])
                return Rows(
                    [
                        {
                            "id": uuid4(),
                            "rule_key": "protected.priya.tuesday",
                            "result": "violation" if params[1] == d0.proposal_id else "pass",
                            "safe_diagnostic": "Exact version only",
                            "fixed_values": {
                                "candidate_digest": versions[params[1]].candidate_digest
                            },
                            "payload": {"family": "reservation"},
                            "source_version_ids": [str(SOURCES["LAUNCH-04"])],
                            "source_title": "Protected capacity",
                            "provider_version": "fixture-1",
                        }
                    ]
                )
            if "default_timezone" in sql:
                return Rows([{"default_timezone": str(ZONE)}])
            raise AssertionError(sql)

    class Store:
        def project(self, *_: Any, connection: Connection) -> Project:
            assert isinstance(connection, Connection)
            return Project(
                id=project_id,
                title="Northstar",
                status="active",
                deadline=None,
                updated_at=START,
                task_count=1,
                completed_task_count=1,
                plan_id=p1.proposal_id,
            )

        def workspace(self, *_: Any) -> Any:
            return SimpleNamespace(viewer=SimpleNamespace(role="manager"))

        @contextmanager
        def transaction(self, *_: Any) -> Any:
            yield Connection()

    store: Any = Store()
    context = CompanyContext(
        actor=AuthenticatedUser(
            user_id=uuid4(), role="authenticated", session_id=uuid4(), assurance_level="aal1"
        ),
        company_id=COMPANY,
        membership_id=uuid4(),
        administrative_role="member",
        employee_id=None,
        demo_run_id=RUN,
        demo_planning_authority=True,
    )
    current = graph(store, context, project_id)
    assert current.nodes[0].title == "Committed title" and not current.is_candidate_preview
    history = graph(store, context, project_id, proposal_id=d0.proposal_id)
    assert history.is_candidate_preview and history.selected_proposal_id == d0.proposal_id
    assert len(history.nodes) == 17 and not any(node.can_work for node in history.nodes)
    assert history.rules[0].status == "violation" and checked_ids[-1] == d0.proposal_id
    assert not history.can_approve and history.plan_id is None
