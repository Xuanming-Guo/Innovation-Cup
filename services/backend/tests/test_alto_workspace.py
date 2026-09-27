"""Final-phase regressions for ALTO's new trust and file-processing boundaries."""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Literal, cast
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.db import demo
from coordination.durable.contracts import JobLease
from coordination.durable.runner import (
    AmbiguousJobOutcomeError,
    PermanentJobError,
    RetryableJobError,
)
from coordination.workspace import files, interactions, jobs, routes, worker_io
from coordination.workspace.contracts import (
    AdvanceClock,
    AssistantActionDecision,
    AssistantContext,
    CalendarData,
    ProfileSkills,
)
from coordination.workspace.persistence import (
    PostgresWorkspaceStore,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
)


def settings(**values: Any) -> Settings:
    return Settings(**{"_env_file": None, "environment": "test", **values})


def context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=uuid4(),
    )


def lease() -> JobLease:
    actor = context()
    return JobLease(
        job_id=uuid4(),
        company_id=actor.company_id,
        job_kind="assistant.respond",
        aggregate_id=uuid4(),
        payload={},
        requested_by_membership_id=actor.membership_id,
        requested_by_user_id=actor.actor.user_id,
        administrative_role="manager",
        employee_id=actor.employee_id,
        correlation_id=uuid4(),
        attempt_count=2,
        max_attempts=3,
        lease_token=uuid4(),
        leased_until=datetime.now(UTC),
        demo_run_id=uuid4(),
        demo_actor_session_id=uuid4(),
        simulated_employee_id=uuid4(),
    )


def test_demo_authority_does_not_inherit_real_manager_role() -> None:
    real = context()
    assert real.can_manage_planning
    selected = replace(real, demo_run_id=uuid4(), simulated_employee_id=uuid4())
    assert not selected.can_manage_planning
    assert selected.effective_employee_id != real.employee_id
    verified = replace(selected, demo_planning_authority=True, administrative_role="member")
    assert verified.can_manage_planning
    assert verified.actor == real.actor
    assert verified.membership_id == real.membership_id


def test_hackathon_quickstart_reuses_live_run_binds_vertex_and_selects_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visitor = context()
    run_id, actor_id, actor_session_id = uuid4(), uuid4(), uuid4()
    queries: list[tuple[str, Any]] = []

    class Result:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self) -> dict[str, Any] | None:
            return self.row

    class Connection:
        def execute(self, query: str, params: Any = None) -> Result:
            queries.append((query, params))
            if "from app.demo_runs" in query:
                return Result({"id": run_id})
            if "from app.employee_profiles" in query:
                return Result({"id": actor_id, "synthetic_key": "iris"})
            if "app.select_demo_actor" in query:
                return Result({"id": actor_session_id})
            return Result()

    store = PostgresWorkspaceStore("postgresql://unused", gemini_model="gemini-demo")
    monkeypatch.setattr(
        store,
        "command",
        lambda request_context, **values: values["operation"](Connection()),
    )

    result = store.quickstart(visitor, "iris", "quickstart-key-0001")

    assert result.run_id == run_id
    assert result.actor_session_id == actor_session_id
    assert result.actor_key == "iris"
    assert any(
        "bind_demo_operator_provider" in query and params[-1] == "gemini-demo"
        for query, params in queries
    )
    assert not any("fork_demo_run" in query for query, _ in queries)


def test_demo_resolution_keeps_authenticated_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    real, selected_employee = context(), uuid4()
    run, actor_session = uuid4(), uuid4()
    recorded: dict[str, Any] = {}

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        recorded.update(kwargs)
        yield SimpleNamespace(
            execute=lambda *args: SimpleNamespace(
                fetchone=lambda: {
                    "value": {"simulated_employee_id": str(selected_employee)},
                    "planning_authority": False,
                }
            )
        )

    monkeypatch.setattr(demo, "company_transaction", transaction)
    selected = demo.resolve_demo_context(
        "postgresql://unused",
        context=real,
        run_id=run,
        actor_session_id=actor_session,
    )
    assert selected.actor == real.actor
    assert selected.administrative_role == "manager"
    assert selected.effective_employee_id == selected_employee
    assert not selected.can_manage_planning
    assert recorded["demo_run_id"] == run
    assert recorded["demo_actor_session_id"] == actor_session


def test_manager_calendar_uses_selected_demo_actor() -> None:
    real = context()
    selected_employee = uuid4()
    selected = replace(
        real,
        demo_run_id=uuid4(),
        demo_actor_session_id=uuid4(),
        simulated_employee_id=selected_employee,
        demo_planning_authority=True,
    )
    first = datetime(2026, 9, 28, tzinfo=UTC)
    expected = CalendarData(items=[], timezone="America/Los_Angeles", sources=[])

    class Store:
        def calendar(
            self,
            request_context: CompanyContext,
            start: datetime,
            end: datetime,
            employee_id: Any,
        ) -> CalendarData:
            assert request_context is selected
            assert start == first
            assert end == first + timedelta(days=7)
            assert employee_id == selected_employee
            return expected

        def workspace(self, *_: Any) -> Any:
            raise AssertionError("calendar scope must not depend on the actor's manager role")

    assert routes.calendar(selected, Store(), first, first + timedelta(days=7)) is expected  # type: ignore[arg-type]


def test_calendar_personal_queries_fail_closed_without_employee_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = replace(context(), employee_id=None)
    first = datetime(2026, 9, 28, tzinfo=UTC)
    calls: list[tuple[str, Any]] = []

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            calls.append((query, params))
            if "select default_timezone" in query:
                return _Rows(one={"default_timezone": "America/Los_Angeles"})
            return _Rows(many=[])

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        yield Connection()

    store = PostgresWorkspaceStore("postgresql://unused.invalid/unused")
    monkeypatch.setattr(store, "transaction", transaction)
    result = store.calendar(actor, first, first + timedelta(days=7), None)

    personal = [
        (query, params)
        for query, params in calls
        if "from app.committed_schedule_blocks" in query
        or "from app.calendar_event_versions" in query
    ]
    assert len(personal) == 2
    for query, params in personal:
        assert "is null or" not in query.lower()
        assert "employee_id=%s" in query
        assert params[-1] is None
    assert result.items == []


def test_profile_declarations_are_bounded_and_do_not_accept_authority_fields() -> None:
    valid = ProfileSkills(expected_row_version=0, skills=[" Writing ", "Design"])
    assert valid.skills == ["Writing", "Design"]
    for body in (
        {"skills": ["Writing", "writing"]},
        {"skills": ["\n"]},
        {"skills": ["x" * 121]},
        {"skills": [], "verified": True},
    ):
        with pytest.raises(ValidationError):
            ProfileSkills.model_validate({"expected_row_version": 0, **body})
    with pytest.raises(ValidationError):
        AdvanceClock(expected_clock_version=1, clock_at=datetime(2026, 9, 28, 9))


def test_assistant_proposal_binding_requires_project_context() -> None:
    proposal_id = uuid4()
    project_id = uuid4()
    assert AssistantContext(
        kind="project", id=project_id, proposal_id=proposal_id
    ).proposal_id == proposal_id
    invalid: tuple[tuple[Literal["global", "task", "person"], Any], ...] = (
        ("global", None),
        ("task", uuid4()),
        ("person", uuid4()),
    )
    for kind, subject_id in invalid:
        with pytest.raises(ValidationError, match="exact proposal"):
            AssistantContext(kind=kind, id=subject_id, proposal_id=proposal_id)


class _Rows:
    def __init__(self, *, one: Any = None, many: list[Any] | None = None) -> None:
        self.one = one
        self.many = many or []

    def fetchone(self) -> Any:
        return self.one

    def fetchall(self) -> list[Any]:
        return self.many


def test_exact_proposal_thread_is_persisted_and_cannot_be_rebound() -> None:
    actor = context()
    project_id, proposal_id, thread_id = uuid4(), uuid4(), uuid4()
    calls: list[tuple[str, Any]] = []

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            calls.append((query, params))
            if "can_bind_assistant_proposal" in query:
                return _Rows(one={"permitted": True})
            if "insert into app.assistant_threads" in query:
                return _Rows(one={"id": thread_id})
            if "select id from app.assistant_threads" in query:
                return _Rows(one={"id": thread_id})
            if "from app.assistant_messages" in query:
                return _Rows(many=[])
            if "from app.assistant_citations" in query:
                return _Rows(many=[])
            if "from app.assistant_action_previews" in query:
                return _Rows(many=[])
            if "from app.durable_jobs" in query:
                return _Rows(one=None)
            if "select context_type,context_id,proposal_id" in query:
                return _Rows(
                    one={
                        "context_type": "project",
                        "context_id": project_id,
                        "proposal_id": proposal_id,
                    }
                )
            raise AssertionError(query)

    connection = Connection()

    class Store:
        def command(self, *args: Any, operation: Any, **kwargs: Any) -> dict[str, Any]:
            return cast(dict[str, Any], operation(connection))

        @contextmanager
        def transaction(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
            yield connection

    binding = AssistantContext(kind="project", id=project_id, proposal_id=proposal_id)
    created = interactions.create_thread(Store(), actor, binding, "proposal-thread-command")  # type: ignore[arg-type]
    assert created["id"] == str(thread_id)
    insert = next(call for call in calls if "insert into app.assistant_threads" in call[0])
    assert insert[1][-1] == proposal_id

    with pytest.raises(WorkspaceConflictError, match="thread context changed"):
        interactions.send_message(
            Store(),  # type: ignore[arg-type]
            actor,
            thread_id,
            "What failed?",
            AssistantContext(kind="project", id=project_id, proposal_id=uuid4()),
            "proposal-message-command",
        )


def test_non_manager_cannot_create_proposal_bound_thread() -> None:
    actor = replace(context(), administrative_role="member")
    with pytest.raises(WorkspaceNotFoundError, match="proposal was not found"):
        interactions.create_thread(
            SimpleNamespace(),  # type: ignore[arg-type]
            actor,
            AssistantContext(kind="project", id=uuid4(), proposal_id=uuid4()),
            "unauthorised-proposal-thread",
        )


def test_assistant_plan_action_response_has_exact_desktop_shape() -> None:
    actor = context()
    thread_id, action_id, project_id, proposal_id = uuid4(), uuid4(), uuid4(), uuid4()
    message_id = uuid4()

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            if "select id from app.assistant_threads" in query:
                return _Rows(one={"id": thread_id})
            if "from app.assistant_messages" in query and "select m.id" in query:
                return _Rows(
                    many=[
                        {
                            "id": message_id,
                            "role": "assistant",
                            "content": "I prepared a reviewable change.",
                            "created_at": datetime.now(UTC),
                            "operation_id": uuid4(),
                        }
                    ]
                )
            if "from app.assistant_citations" in query:
                return _Rows(many=[])
            if "from app.assistant_action_previews" in query:
                return _Rows(
                    many=[
                        {
                            "id": action_id,
                            "command_type": "plan_change",
                            "state": "pending_confirmation",
                            "title": "Prepare a revised plan",
                            "summary": "Move the QA review.",
                            "project_id": project_id,
                            "proposal_id": proposal_id,
                            "plan_id": None,
                            "expected_version": 2,
                            "row_version": 1,
                            "expires_at": datetime.now(UTC) + timedelta(minutes=10),
                            "action_payload": {
                                "scope": [
                                    {"label": "Project", "value": str(project_id)},
                                    {"label": "Exact proposal", "value": str(proposal_id)},
                                ],
                                "changes": [
                                    {
                                        "id": "manager-request",
                                        "label": "Requested change",
                                        "field": "schedule",
                                        "before": "Current exact proposal",
                                        "after": "Move the QA review.",
                                    }
                                ],
                                "violations": [
                                    {
                                        "id": "capacity.priya",
                                        "title": "Capacity Priya",
                                        "status": "violation",
                                        "description": "Recorded rule did not pass.",
                                        "formula": None,
                                        "source_label": None,
                                        "source_version": None,
                                        "candidate_values": None,
                                    }
                                ],
                                "warnings": ["No work changes before confirmation."],
                                "executable": False,
                                "result_target_path": (
                                    f"/projects/{project_id}/graph?proposal_id={proposal_id}"
                                ),
                            },
                            "result": None,
                        }
                    ]
                )
            if "from app.durable_jobs" in query:
                return _Rows(one=None)
            raise AssertionError(query)

    class Store:
        @contextmanager
        def transaction(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
            yield Connection()

    response = interactions.get_thread(Store(), actor, thread_id)  # type: ignore[arg-type]
    action = response["pending_actions"][0]
    assert action["scope"] == [
        {"label": "Project", "value": str(project_id)},
        {"label": "Exact proposal", "value": str(proposal_id)},
    ]
    assert action["changes"] == [
        {
            "id": "manager-request",
            "label": "Requested change",
            "field": "schedule",
            "before": "Current exact proposal",
            "after": "Move the QA review.",
        }
    ]
    assert action["violations"][0]["status"].lower() == "violation"
    assert action["confirmation"]["expected_version"] == 1
    assert action["confirmation"]["label"] == "Open plan review"
    assert "does not change or assign work" in action["confirmation"]["consequence"]
    assert action["result_target_path"].startswith(f"/projects/{project_id}/graph?")


def test_assistant_action_requires_current_manager_and_explicit_decision() -> None:
    decision = AssistantActionDecision(decision="confirm", expected_version=1)
    assert decision.decision == "confirm"
    with pytest.raises(ValidationError):
        AssistantActionDecision.model_validate({"decision": "confirm", "expected_version": 0})
    actor = replace(context(), administrative_role="member")
    with pytest.raises(WorkspaceNotFoundError, match="action was not found"):
        interactions.decide_action(
            cast(PostgresWorkspaceStore, SimpleNamespace()),
            actor,
            uuid4(),
            uuid4(),
            decision,
            "confirm-action-command",
        )


@pytest.mark.parametrize(
    "data,mime",
    [
        (b"", "text/plain"),
        (b"hello\0", "text/plain"),
        (b"invalid", "application/pdf"),
        (b"%PDF-1.7 missing end", "application/pdf"),
        (b"data", "application/x-executable"),
        (b"not a PNG", "image/png"),
        (b"not audio", "audio/webm"),
    ],
)
def test_file_validation_rejects_false_types(data: bytes, mime: str) -> None:
    with pytest.raises(ValueError):
        files.validate_file(data, mime, settings())


def test_docx_structure_and_active_content_are_validated() -> None:
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    for extra in (None, "word/vbaProject.bin", "../escape.txt"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr("word/document.xml", "<document />")
            if extra:
                archive.writestr(extra, "untrusted")
        if extra:
            with pytest.raises(ValueError, match="docx_active_content"):
                files.validate_file(stream.getvalue(), mime, settings())
        else:
            assert files.validate_file(stream.getvalue(), mime, settings()) == {}


def test_recorded_webm_duration_comes_from_decoded_packets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata: dict[str, Any] = {
        "streams": [{"codec_type": "audio"}],
        "format": {},
        "packets": [
            {"pts_time": "0", "duration_time": "0.02"},
            {"pts_time": "12.98", "duration_time": "0.02"},
        ],
    }

    def probe(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 15
        assert "-protocol_whitelist" in args[0]
        return subprocess.CompletedProcess(args[0], 0, json.dumps(metadata).encode(), b"")

    monkeypatch.setattr("coordination.workspace.files.subprocess.run", probe)
    payload = b"\x1a\x45\xdf\xa3recording"
    assert files.validate_file(payload, "audio/webm", settings()) == {
        "audio_duration_seconds": 13.0,
    }
    metadata["packets"][-1]["pts_time"] = "60.01"
    with pytest.raises(ValueError, match="audio_duration"):
        files.validate_file(payload, "audio/webm", settings())
    metadata["streams"] = [{"codec_type": "video"}]
    with pytest.raises(ValueError, match="audio_tracks"):
        files.validate_file(payload, "audio/webm", settings())


@pytest.mark.parametrize(
    "verdict,expected",
    [
        (b"stream: OK\0", "clean"),
        (b"stream: Eicar-Test-Signature FOUND\0", "rejected"),
        (b"stream: read ERROR\0", "retry"),
        (b"", "retry"),
    ],
)
def test_scanner_only_exact_clean_verdict_publishes(
    monkeypatch: pytest.MonkeyPatch,
    verdict: bytes,
    expected: str,
) -> None:
    replies = iter([b"ClamAV 1.4/test\0", verdict])
    sent: list[bytes] = []

    @contextmanager
    def connect(*args: Any, **kwargs: Any) -> Iterator[Any]:
        reply = next(replies)
        yield SimpleNamespace(sendall=sent.append, recv=lambda size: reply)

    monkeypatch.setattr("coordination.workspace.files.socket.create_connection", connect)
    if expected == "retry":
        with pytest.raises(RetryableJobError, match="file_scanner_incomplete"):
            files.clam_scan(b"test", settings(file_scanner_host="internal-scanner"))
    else:
        assert (
            files.clam_scan(b"test", settings(file_scanner_host="internal-scanner"))[0] == expected
        )
    assert b"zINSTREAM\0" in sent
    assert sent[-1] == b"\0\0\0\0"


def test_worker_storage_cannot_follow_foreign_capability_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = worker_io.WorkerStorage(
        settings(supabase_url="https://example.supabase.co"), lease(), uuid4()
    )
    response = httpx.Response(
        200,
        json={"signed_url": "https://attacker.invalid/file"},
        request=httpx.Request("POST", "https://example.supabase.co"),
    )
    monkeypatch.setattr(
        "coordination.workspace.worker_io.httpx.post", lambda *args, **kwargs: response
    )
    with pytest.raises(PermanentJobError, match="storage_origin_mismatch"):
        storage.ticket("download-quarantine")


def test_model_ambiguity_never_repeats_uncheckpointed_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[Any] = []

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        def execute(query: str, params: Any) -> Any:
            queries.append((query, params))
            return SimpleNamespace(fetchall=lambda: [{"status": "running"}])

        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(jobs, "job_transaction", transaction)
    handler = jobs.WorkspaceJobHandler(
        settings(database_url="postgresql://unused:unused@localhost/unused"),
        "assistant.respond",
    )
    with pytest.raises(AmbiguousJobOutcomeError, match="model_attempt_already_recorded"):
        handler.begin(lease(), {"safe": True}, SimpleNamespace())
    assert len(queries) == 1
    assert len(queries[0][1][1]) == 2


def test_assistant_projection_contains_only_exact_recorded_candidate_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id, project_id, proposal_id, verification_id = uuid4(), uuid4(), uuid4(), uuid4()
    exact_lease = lease().model_copy(update={"payload": {"thread_id": str(thread_id)}})

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            if "from app.assistant_threads" in query:
                return _Rows(
                    one={
                        "context_type": "project",
                        "context_id": project_id,
                        "proposal_id": proposal_id,
                    }
                )
            if "from app.assistant_messages" in query:
                return _Rows(many=[{"role": "user", "content": "What are the violations?"}])
            if "from app.source_records" in query:
                return _Rows(many=[])
            if "from app.projects" in query:
                return _Rows(many=[{"id": project_id, "title": "Exact project"}])
            if "from app.work_items" in query:
                return _Rows(many=[])
            if "from app.ai_plan_proposals" in query:
                assert params == (exact_lease.company_id, proposal_id, project_id)
                return _Rows(
                    one={
                        "id": proposal_id,
                        "version": 2,
                        "author_kind": "ai_authored",
                        "candidate_digest": "ab" * 32,
                        "verification_id": verification_id,
                        "product_status": "VIOLATIONS_FOUND",
                        "native_status": "unsat",
                        "required_rule_count": 7,
                        "covered_rule_count": 7,
                        "unverified_rule_ids": [],
                        "independent_validation_passed": None,
                        "independent_validation_issues": None,
                    }
                )
            if "from app.plan_verification_rule_results" in query:
                assert params == (exact_lease.company_id, verification_id)
                assert "result.result in ('violation','unable')" in query
                return _Rows(
                    many=[
                        {
                            "rule_key": "capacity.priya",
                            "result": "violation",
                            "safe_diagnostic": "Recorded fixed candidate rule did not pass.",
                            "source_title": None,
                            "source_provider_version": None,
                        }
                    ]
                )
            if "from app.demo_runs" in query:
                return _Rows(one={"mode": "live"})
            raise AssertionError(query)

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        yield Connection()

    monkeypatch.setattr(jobs, "job_transaction", transaction)
    handler = jobs.WorkspaceJobHandler(
        settings(database_url="postgresql://unused:unused@localhost/unused"),
        "assistant.respond",
    )
    projection = handler.projection(exact_lease)
    candidate = projection["subject"]["exact_candidate"]
    assert candidate["id"] == proposal_id
    assert candidate["product_status"] == "VIOLATIONS_FOUND"
    assert candidate["non_passing_rules"] == [
        {
            "rule_key": "capacity.priya",
            "result": "violation",
            "safe_diagnostic": "Recorded fixed candidate rule did not pass.",
            "source_title": None,
            "source_provider_version": None,
        }
    ]
    encoded = json.dumps(projection, default=str)
    assert "verification_id" not in encoded
    assert "candidate_payload" not in encoded
    assert "solver_trace" not in encoded


def test_worker_stages_plan_change_as_typed_preview_without_executing() -> None:
    exact_lease = lease()
    project_id, proposal_id, message_id = uuid4(), uuid4(), uuid4()
    calls: list[tuple[str, Any]] = []

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            calls.append((query, params))
            return _Rows()

    handler = jobs.WorkspaceJobHandler(
        settings(database_url="postgresql://unused:unused@localhost/unused"),
        "assistant.respond",
    )
    action_id = handler.stage_action(
        Connection(),
        exact_lease,
        {
            "context": {
                "context_type": "project",
                "context_id": project_id,
                "proposal_id": proposal_id,
            },
            "subject": {
                "exact_candidate": {
                    "id": proposal_id,
                    "version": 2,
                    "plan_id": None,
                    "available_actions": ["plan_change"],
                    "non_passing_rules": [
                        {
                            "rule_key": "capacity.priya",
                            "result": "violation",
                            "safe_diagnostic": "Recorded fixed candidate rule did not pass.",
                            "source_title": None,
                            "source_provider_version": None,
                        }
                    ],
                }
            },
            "messages": [{"role": "user", "content": "Move Priya's review."}],
            "sources": [],
            "mode": "live",
        },
        message_id,
        jobs.AssistantActionSuggestion(
            kind="plan_change", instruction="Move Priya's review."
        ),
    )
    assert action_id is not None
    insert = calls[0]
    payload = insert[1][-1].obj
    assert payload["scope"] == [
        {"label": "Project", "value": str(project_id)},
        {"label": "Exact proposal", "value": str(proposal_id)},
    ]
    assert payload["changes"][0] == {
        "id": "manager-request",
        "label": "Requested change",
        "field": "schedule",
        "before": "Current exact proposal",
        "after": "Move Priya's review.",
    }
    assert payload["violations"][0]["status"] == "violation"
    assert payload["executable"] is False
    assert "insert into app.assistant_action_previews" in insert[0]


def test_assistant_projection_fails_closed_when_exact_proposal_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id, project_id, proposal_id = uuid4(), uuid4(), uuid4()
    exact_lease = lease().model_copy(update={"payload": {"thread_id": str(thread_id)}})

    class Connection:
        def execute(self, query: str, params: Any = None) -> _Rows:
            if "from app.assistant_threads" in query:
                return _Rows(
                    one={
                        "context_type": "project",
                        "context_id": project_id,
                        "proposal_id": proposal_id,
                    }
                )
            if "from app.assistant_messages" in query or "from app.source_records" in query:
                return _Rows(many=[])
            if "from app.projects" in query or "from app.work_items" in query:
                return _Rows(many=[])
            if "from app.ai_plan_proposals" in query:
                return _Rows(one=None)
            raise AssertionError(query)

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        yield Connection()

    monkeypatch.setattr(jobs, "job_transaction", transaction)
    handler = jobs.WorkspaceJobHandler(
        settings(database_url="postgresql://unused:unused@localhost/unused"),
        "assistant.respond",
    )
    with pytest.raises(PermanentJobError, match="assistant_context_unavailable"):
        handler.projection(exact_lease)
