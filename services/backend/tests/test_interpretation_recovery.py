from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr, ValidationError

from coordination.ai_rate_limit import GeminiRequestLimiter
from coordination.config import Settings
from coordination.durable import handlers
from coordination.durable.contracts import JobLease
from coordination.durable.runner import PermanentJobError, RetryableJobError
from coordination.interpretation import persistence as interpretation_persistence
from coordination.interpretation.admission import AdmissionResult
from coordination.interpretation.contracts import CandidateTaskContract
from coordination.interpretation.gateway import (
    GatewayConfiguration,
    GatewayResponse,
    GeminiInvalidOutputError,
    GeminiRefusalError,
    GeminiTruncatedOutputError,
    GoogleGeminiGateway,
    ModelUsage,
)
from coordination.interpretation.persistence import PostgresInterpretationStore
from coordination.interpretation.projection import InterpretationProjection
from coordination.interpretation.prompt import (
    InterpretationRepairContext,
    InterpretationRepairIssue,
    build_interpretation_prompt,
)
from coordination.interpretation.service import (
    InterpretationBudgetExceededError,
    InterpretationOutcome,
    InterpretationService,
)
from coordination.planning.northstar import NORTHSTAR_INTAKE, build_northstar_contract
from coordination.planning.northstar_authority import (
    admit_live_northstar_contract,
    canonical_authority_manifest,
)
from coordination.planning.persistence import PlanningStateConflictError
from coordination.workspace import northstar

COMPANY = UUID(int=101)
RUN = UUID(int=102)
REQUEST = UUID(int=103)
SOURCES = {f"LAUNCH-{index:02}": UUID(int=index) for index in range(1, 8)}
NOW = datetime(2026, 9, 27, tzinfo=UTC)


def contract(*, wrong_owner: bool = False) -> CandidateTaskContract:
    result = build_northstar_contract(
        company_id=COMPANY,
        request_id=REQUEST,
        source_version_ids=SOURCES,
    )
    payload = result.model_dump(mode="json")
    for task in payload["tasks"]:
        if task["task_key"] in {"d1", "m2"}:
            task["requirements"] = [
                {
                    "requirement_key": "northstar.jules" if wrong_owner else "northstar.iris",
                    "kind": "skill",
                    "strength": "hard",
                    "minimum_level": None,
                    "description": "The authoritative eligible owner must perform this work.",
                    "bases": [
                        {
                            "kind": "evidence",
                            "source_version_id": str(SOURCES["LAUNCH-07"]),
                            "locator": "LAUNCH-07",
                            "claim": "Named task eligibility.",
                        }
                    ],
                }
            ]
    return CandidateTaskContract.model_validate(payload)


def projection() -> InterpretationProjection:
    return InterpretationProjection.model_validate(
        {
            "projection_version": "interpretation-projection.v1",
            "company_id": COMPANY,
            "request_id": REQUEST,
            "request_version": 1,
            "original_request": NORTHSTAR_INTAKE,
            "retrieved_at": NOW,
            "requested_priority_key": None,
            "requested_deadline": None,
            "requested_deadline_timezone": None,
            "sources": [
                {
                    "source_id": UUID(int=1000 + index),
                    "source_version_id": source_id,
                    "source_kind": "fixture",
                    "authority_status": "authoritative",
                    "classification": "internal",
                    "retrieved_at": NOW,
                    "expires_at": None,
                    "freshness": "current",
                    "content_sha256_hex": sha256(key.encode()).hexdigest(),
                    "excerpts": [{"locator": key, "text": key}],
                }
                for index, (key, source_id) in enumerate(SOURCES.items())
            ],
            "employees": [],
            "commitments": [],
            "capacity": [],
            "dependencies": [],
            "supported_constraint_types": ["effort", "eligibility"],
            "missing_data": [],
        }
    )


def admission(value: CandidateTaskContract) -> AdmissionResult:
    return admit_live_northstar_contract(
        company_id=COMPANY,
        request_id=REQUEST,
        contract=value,
        source_version_ids=SOURCES,
        authority=canonical_authority_manifest(),
    )


def authority_adapter() -> northstar.LiveNorthstarAdmission:
    return northstar.LiveNorthstarAdmission(
        company_id=COMPANY,
        request_id=REQUEST,
        request_version=1,
        authority=canonical_authority_manifest(),
        source_version_ids=SOURCES,
        source_rows=(),
    )


def repair_context(outcome: InterpretationOutcome) -> InterpretationRepairContext:
    return InterpretationRepairContext(
        previous_contract_digest=outcome.contract_digest,
        issues=tuple(
            InterpretationRepairIssue(code=issue.code, path=issue.path)
            for issue in outcome.admission.issues
        ),
    )


class Recorder:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.completed: list[InterpretationOutcome] = []
        self.failed: list[dict[str, Any]] = []

    def start(self, **values: Any) -> None:
        self.started.append(values)

    def complete(self, outcome: InterpretationOutcome, **_: Any) -> None:
        self.completed.append(outcome)

    def fail(self, **values: Any) -> None:
        self.failed.append(values)


class Gateway:
    configuration = GatewayConfiguration(model="gemini-test", max_output_tokens=16384)

    def __init__(self, responses: list[CandidateTaskContract | Exception]) -> None:
        self.responses = responses
        self.calls = 0
        self.feedback: list[InterpretationRepairContext] = []

    def generate(self, _: InterpretationProjection) -> GatewayResponse:
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return GatewayResponse(
            contract=response,
            model_version="gemini-test",
            provider_response_id=None,
            sdk_version="test",
            finish_reason="STOP",
            usage=ModelUsage(
                prompt_tokens=10, candidate_tokens=10, total_tokens=20, thought_tokens=0
            ),
        )

    def generate_with_repair(
        self,
        value: InterpretationProjection,
        *,
        repair_context: InterpretationRepairContext,
    ) -> GatewayResponse:
        self.feedback.append(repair_context)
        return self.generate(value)


def test_wrong_background_owner_is_rejected_before_any_admitted_handoff() -> None:
    wrong = contract(wrong_owner=True)
    original = wrong.model_dump_json()
    recorder = Recorder()
    outcome = InterpretationService(
        gateway=Gateway([wrong]),
        recorder=recorder,
        admission_validator=admission,
        clock=lambda: NOW,
    ).interpret(projection())
    assert outcome.status == "rejected"
    assert len(outcome.admission.issues) == 2
    assert {issue.code for issue in outcome.admission.issues} == {"finite_requirement_mismatch"}
    assert all("northstar.iris" in issue.message for issue in outcome.admission.issues)
    assert recorder.completed == [outcome]
    assert wrong.model_dump_json() == original
    assert outcome.response.contract == wrong
    assert admission(contract()).status == "admitted"


def test_repair_uses_codes_paths_and_immutable_digest_without_mutating_prior_candidate() -> None:
    wrong = contract(wrong_owner=True)
    recorder = Recorder()
    gateway = Gateway([wrong, contract()])
    rejected = InterpretationService(
        gateway=gateway,
        recorder=recorder,
        admission_validator=admission,
        clock=lambda: NOW,
    ).interpret(projection())
    original_feedback = repair_context(rejected)
    feedback = authority_adapter().with_repair_requirements(original_feedback)
    assert feedback.digest != original_feedback.digest
    admitted = InterpretationService(
        gateway=gateway,
        recorder=recorder,
        admission_validator=admission,
        repair_context=feedback,
        clock=lambda: NOW,
    ).interpret(projection())
    assert admitted.status == "admitted"
    assert gateway.calls == 2 and gateway.feedback == [feedback]
    assert recorder.completed[0].response.contract == wrong
    config = recorder.started[-1]["configuration"].ledger_values()
    assert config["interpretation_context_digest"] == feedback.digest
    assert config["max_output_tokens"] == 16384 and config["retry_attempts"] == 1
    prompt = build_interpretation_prompt(projection(), repair_context=feedback)
    assert feedback.canonical_json() in prompt
    assert "previous_contract_digest" in prompt
    assert "northstar.jules" not in feedback.canonical_json()
    assert "message" not in feedback.canonical_json()
    assert feedback.requirement_authority is not None
    authority = feedback.requirement_authority
    assert authority.source_version_id == SOURCES["LAUNCH-07"]
    assert authority.locator == "LAUNCH-07" and len(authority.tasks) == 17
    by_key = {task.task_key: task for task in authority.tasks}
    assert by_key["d1"].skill_or_qualification_keys == ("northstar.iris",)
    assert by_key["m2"].skill_or_qualification_keys == ("northstar.iris",)
    assert all(task.permission_or_input_keys == ("northstar.launch",) for task in authority.tasks)
    assert all(task.minimum_level is None for task in authority.tasks)
    assert {task.task_key: task.review_keys for task in authority.tasks} == {
        task.task_key: task.review_task_keys for task in canonical_authority_manifest().tasks
    }
    assert "requirement_authority" not in build_interpretation_prompt(projection())


def test_typed_repair_lookup_is_included_in_the_existing_input_budget() -> None:
    feedback = authority_adapter().with_repair_requirements(
        InterpretationRepairContext(
            previous_contract_digest="ab" * 32,
            issues=(
                InterpretationRepairIssue(code="finite_requirement_mismatch", path="tasks[0]"),
            ),
        )
    )
    gateway, recorder = Gateway([contract()]), Recorder()
    with pytest.raises(InterpretationBudgetExceededError):
        InterpretationService(
            gateway=gateway,
            recorder=recorder,
            repair_context=feedback,
            max_projection_characters=len(projection().canonical_json()) + 1,
            clock=lambda: NOW,
        ).interpret(projection())
    assert gateway.calls == 0
    assert recorder.failed[-1]["error_code"] == "projection_budget_exhausted"
    assert recorder.started[-1]["configuration"].interpretation_context_digest == feedback.digest


@pytest.mark.parametrize("code", ["stale_source", "source_not_permitted", "material_assumption"])
def test_repair_context_cannot_promote_authority_failures_to_model_instructions(code: str) -> None:
    with pytest.raises(ValidationError):
        InterpretationRepairIssue(code=code, path="tasks[0].bases")


def lease(attempt: int = 1) -> JobLease:
    return JobLease(
        job_id=UUID(int=104),
        company_id=COMPANY,
        job_kind="interpretation.run",
        aggregate_id=REQUEST,
        payload={"request_id": str(REQUEST)},
        requested_by_membership_id=UUID(int=105),
        requested_by_user_id=UUID(int=106),
        administrative_role="manager",
        employee_id=UUID(int=107),
        correlation_id=UUID(int=108),
        attempt_count=attempt,
        max_attempts=6,
        lease_token=UUID(int=109),
        leased_until=NOW + timedelta(minutes=10),
        demo_run_id=RUN,
        demo_actor_session_id=UUID(int=110),
        simulated_employee_id=UUID(int=111),
    )


class Store:
    def __init__(self) -> None:
        self.results = Recorder()

    def get_worker_request_state(self, **_: Any) -> Any:
        state = "pending_interpretation"
        if self.results.completed:
            state = "failed" if self.results.completed[-1].status == "rejected" else "interpreted"
        elif self.results.failed:
            state = "failed"
        return SimpleNamespace(status=state, candidate_digest=None)

    def load_projection(self, **_: Any) -> Any:
        return SimpleNamespace(projection=projection())

    def recorder(self, **_: Any) -> Recorder:
        return self.results

    def load_repair_context(self, **_: Any) -> InterpretationRepairContext | None:
        return repair_context(self.results.completed[-1]) if self.results.completed else None


def handler(
    monkeypatch: pytest.MonkeyPatch,
    gateway: Gateway,
    store: Store,
) -> handlers.InterpretationJobHandler:
    monkeypatch.setattr(handlers, "load_run_mode", lambda **_: "live")
    monkeypatch.setattr(handlers, "load_live_northstar_admission", lambda **_: authority_adapter())
    return handlers.InterpretationJobHandler(
        settings=Settings(
            database_url=SecretStr("postgresql://unused.invalid/test"),
            hackathon_demo=False,
        ),
        store=cast(PostgresInterpretationStore, store),
        gateway_factory=lambda _: gateway,
    )


def test_durable_retry_repairs_once_then_hands_off_only_the_corrected_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, store = Gateway([contract(wrong_owner=True), contract()]), Store()
    run = handler(monkeypatch, gateway, store)
    with pytest.raises(RetryableJobError, match="interpretation_contract_repair"):
        run(lease())
    assert store.results.completed[0].status == "rejected"
    result = run(lease(2))
    assert result.values["status"] == "admitted"
    assert len(gateway.feedback) == 1 and gateway.calls == 2
    assert gateway.feedback[0].requirement_authority is not None
    assert gateway.feedback[0].requirement_authority.source_version_id == SOURCES["LAUNCH-07"]
    assert run(lease(3)).values["reconciled"] is True
    assert gateway.calls == 2


def test_locked_hackathon_demo_uses_authored_interpretation_without_provider_or_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, store = Gateway([AssertionError("provider must not be called")]), Store()
    limiter = SimpleNamespace(
        wait_until_available=lambda: (_ for _ in ()).throw(
            AssertionError("provider limiter must not be called")
        )
    )
    monkeypatch.setattr(handlers, "load_run_mode", lambda **_: "live")
    monkeypatch.setattr(
        handlers, "load_live_northstar_admission", lambda **_: authority_adapter()
    )
    run = handlers.InterpretationJobHandler(
        settings=Settings(
            database_url=SecretStr("postgresql://unused.invalid/test"),
            hackathon_demo=True,
        ),
        store=cast(PostgresInterpretationStore, store),
        gateway_factory=lambda _: gateway,
        request_limiter=cast(GeminiRequestLimiter, limiter),
    )

    result = run(lease())

    assert result.values["status"] == "admitted"
    assert gateway.calls == 0
    assert store.results.completed[0].response.model_version.startswith("authored:")
    assert store.results.completed[0].response.usage.total_tokens == 0


def test_locked_hackathon_demo_materializes_the_authored_contract_without_live_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_id = UUID(int=112)
    candidate_id = UUID(int=113)
    calls: list[tuple[UUID, UUID]] = []
    materializer = SimpleNamespace(
        materialize=lambda **_: (_ for _ in ()).throw(
            AssertionError("generic materialization must not be called")
        )
    )
    monkeypatch.setattr(handlers, "load_run_mode", lambda **_: "live")
    monkeypatch.setattr(handlers, "_assert_planning_lease", lambda *_: None)

    def authored_materialization(**values: Any) -> UUID:
        calls.append((values["context"].demo_run_id, values["candidate_contract_id"]))
        return snapshot_id

    monkeypatch.setattr(handlers, "materialize_northstar_snapshot", authored_materialization)
    run = handlers.CandidateMaterializationJobHandler(
        cast(Any, materializer),
        settings=Settings(
            database_url=SecretStr("postgresql://unused.invalid/test"),
            hackathon_demo=True,
        ),
    )
    job = lease().model_copy(
        update={
            "job_kind": "planning.materialize",
            "payload": {"candidate_contract_id": str(candidate_id)},
        }
    )

    result = run(job)

    assert result.values == {
        "candidate_contract_id": str(candidate_id),
        "snapshot_id": str(snapshot_id),
    }
    assert calls == [(RUN, candidate_id)]


def test_third_invalid_contract_stops_and_fourth_attempt_never_calls_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway, store = Gateway([contract(wrong_owner=True)] * 3), Store()
    run = handler(monkeypatch, gateway, store)
    for attempt in (1, 2):
        with pytest.raises(RetryableJobError):
            run(lease(attempt))
    with pytest.raises(PermanentJobError, match="interpretation_contract_rejected"):
        run(lease(3))
    with pytest.raises(PermanentJobError, match="interpretation_repair_budget_exhausted"):
        run(lease(4))
    assert gateway.calls == 3 and len(store.results.completed) == 3
    assert lease().max_attempts == 6


@pytest.mark.parametrize("error_type", [GeminiInvalidOutputError, GeminiTruncatedOutputError])
def test_schema_and_truncation_retries_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    gateway, store = Gateway([error_type("invalid")] * 3), Store()
    run = handler(monkeypatch, gateway, store)
    for attempt in (1, 2):
        with pytest.raises(RetryableJobError):
            run(lease(attempt))
    with pytest.raises(PermanentJobError):
        run(lease(3))
    assert gateway.calls == 3 and len(store.results.failed) == 3
    assert not store.results.completed


def test_provider_refusal_is_not_automatically_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, store = Gateway([GeminiRefusalError("refused")]), Store()
    with pytest.raises(PermanentJobError, match="model_refusal"):
        handler(monkeypatch, gateway, store)(lease())
    assert gateway.calls == 1


def test_unpermitted_source_is_a_terminal_rejection_not_a_technical_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = contract().model_dump(mode="json")
    payload["tasks"][0]["bases"][0]["source_version_id"] = str(UUID(int=999))
    gateway, store = Gateway([CandidateTaskContract.model_validate(payload)]), Store()
    with pytest.raises(PermanentJobError, match="interpretation_contract_rejected"):
        handler(monkeypatch, gateway, store)(lease())
    assert store.results.completed[0].admission.issues[0].code == "source_not_permitted"
    assert gateway.calls == 1


def test_material_assumption_remains_a_real_human_question(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = contract().model_dump(mode="json")
    payload["assumptions"] = [
        {
            "assumption_id": "extra_authority",
            "statement": "An additional authority decision exists.",
            "material": True,
            "authority_required": "project_manager",
        }
    ]
    gateway, store = Gateway([CandidateTaskContract.model_validate(payload)]), Store()
    result = handler(monkeypatch, gateway, store)(lease())
    assert result.values["status"] == "clarification_required"
    assert gateway.calls == 1


def test_changed_authority_stops_before_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway, store = Gateway([contract()]), Store()
    run = handler(monkeypatch, gateway, store)

    def unavailable(**_: Any) -> Any:
        raise PlanningStateConflictError("source access changed")

    monkeypatch.setattr(handlers, "load_live_northstar_admission", unavailable)
    monkeypatch.setattr(
        store, "get_worker_request_state", lambda **_: SimpleNamespace(status="failed")
    )

    def must_not_read_feedback(**_: Any) -> Any:
        raise AssertionError("denied source authority must prevent repair-context retrieval")

    monkeypatch.setattr(store, "load_repair_context", must_not_read_feedback)
    with pytest.raises(PermanentJobError, match="interpretation_authority_unavailable"):
        run(lease(2))
    assert gateway.calls == 0 and not store.results.started


class Connection:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, Any]] = []

    def execute(self, sql: str, values: Any = None) -> Any:
        self.calls.append((" ".join(sql.split()), values))
        row = self.rows.pop(0)
        return SimpleNamespace(fetchone=lambda: row, fetchall=lambda: row)


def install_connection(
    monkeypatch: pytest.MonkeyPatch, module: Any, connection: Connection
) -> list[Any]:
    scopes: list[Any] = []

    @contextmanager
    def transaction(*_: Any, **kwargs: Any) -> Iterator[Connection]:
        scopes.append(kwargs)
        yield connection

    monkeypatch.setattr(module, "company_transaction", transaction)
    return scopes


@pytest.mark.parametrize("available", [False, True])
def test_repair_feedback_query_is_exact_scope_and_drops_raw_messages(
    monkeypatch: pytest.MonkeyPatch,
    available: bool,
) -> None:
    row = (
        {
            "contract_digest": bytes.fromhex("ab" * 32),
            "validation_issues": [
                {
                    "code": "finite_requirement_mismatch",
                    "path": "tasks[0].requirements[0]",
                    "disposition": "reject",
                    "message": "DO NOT INCLUDE PRIVATE SOURCE TEXT",
                }
            ],
        }
        if available
        else None
    )
    connection = Connection([row])
    scopes = install_connection(monkeypatch, interpretation_persistence, connection)
    context = lease().company_context()
    result = PostgresInterpretationStore("unused").load_repair_context(
        context=context, request_id=REQUEST
    )
    sql, params = connection.calls[0]
    assert "candidate.demo_run_id is not distinct from %s" in sql
    assert "request.demo_run_id is not distinct from %s" in sql
    assert "candidate.admission_status='rejected'" in sql
    assert params == (COMPANY, REQUEST, RUN, RUN)
    assert scopes[0]["demo_actor_session_id"] == context.demo_actor_session_id
    if available:
        assert result is not None and "PRIVATE" not in result.canonical_json()
    else:
        assert result is None


def authenticated_rows() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sources: list[dict[str, Any]] = [{"key": key, "text": key} for key in SOURCES]
    sources[-1]["planning_authority"] = canonical_authority_manifest().model_dump(mode="json")
    payload = {"sources": sources}
    manifest = {
        "manifest_payload": payload,
        "manifest_digest": sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest(),
    }
    rows = [
        {
            "source_id": source.source_id,
            "source_version_id": source.source_version_id,
            "locator": source.excerpts[0].locator,
            "permitted_text": source.excerpts[0].text,
            "content_sha256": bytes.fromhex(source.content_sha256_hex),
            "text_sha256": bytes.fromhex(source.content_sha256_hex),
        }
        for source in projection().sources
    ]
    return manifest, rows


@pytest.mark.parametrize("tamper", [None, "manifest", "content", "inaccessible", "projection"])
def test_live_finite_adapter_requires_lease_pinned_manifest_and_exact_current_sources(
    monkeypatch: pytest.MonkeyPatch,
    tamper: str | None,
) -> None:
    manifest, source_rows = authenticated_rows()
    projected = projection()
    if tamper == "manifest":
        manifest["manifest_digest"] = "00" * 32
    elif tamper == "content":
        source_rows[0]["permitted_text"] = "changed"
    elif tamper == "inaccessible":
        source_rows.pop()
    elif tamper == "projection":
        projected = projected.model_copy(update={"sources": projected.sources[:-1]})
    connection = Connection(
        [
            None,
            {"value": manifest},
            {
                "original_prompt": NORTHSTAR_INTAKE,
                "request_version": 1,
            },
            source_rows,
        ]
    )
    scopes = install_connection(monkeypatch, northstar, connection)
    context = lease().company_context()

    def load() -> northstar.LiveNorthstarAdmission:
        return northstar.load_live_northstar_admission(
            dsn="unused",
            context=context,
            projection=projected,
            job_id=lease().job_id,
            lease_token=lease().lease_token,
        )

    if tamper:
        with pytest.raises(PlanningStateConflictError):
            load()
    else:
        result = load()
        assert result.admit(contract()).status == "admitted"
        feedback = result.with_repair_requirements(
            InterpretationRepairContext(
                previous_contract_digest="ab" * 32,
                issues=(
                    InterpretationRepairIssue(code="finite_requirement_mismatch", path="tasks[0]"),
                ),
            )
        )
        assert feedback.requirement_authority is not None
        assert feedback.requirement_authority.source_version_id == SOURCES["LAUNCH-07"]
        assert next(
            task for task in feedback.requirement_authority.tasks if task.task_key == "d1"
        ).skill_or_qualification_keys == ("northstar.iris",)
        sql = connection.calls[-1][0]
        assert "app.can_read_source" in sql and "version.expires_at>clock_timestamp()" in sql
        assert "source.current_version_id=selected.source_version_id" in sql
    assert connection.calls[0][1] == (str(lease().job_id), str(lease().lease_token))
    assert "app.get_demo_scenario_manifest" in connection.calls[1][0]
    assert scopes[0]["company_id"] == COMPANY and scopes[0]["demo_run_id"] == RUN


def test_google_gateway_transmits_only_safe_repair_envelope() -> None:
    calls: list[dict[str, Any]] = []

    def generate_content(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(
            parsed=contract(),
            model_version="test",
            response_id=None,
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=None,
        )

    gateway = GoogleGeminiGateway(
        configuration=GatewayConfiguration(model="gemini-test"),
        client=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
    )
    feedback = InterpretationRepairContext(
        previous_contract_digest="ab" * 32,
        issues=(
            InterpretationRepairIssue(
                code="finite_requirement_mismatch", path="tasks[0].requirements[0]"
            ),
        ),
    )
    result = gateway.generate_with_repair(projection(), repair_context=feedback)
    assert result.contract == contract()
    assert feedback.canonical_json() in calls[0]["contents"]
    assert len(calls) == 1
