from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import psycopg
import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.interpretation import persistence as persistence_module
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    PlanningRequestIdempotencyConflictError,
    PostgresInterpretationStore,
    SubmitClarificationAnswers,
)

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MEMBERSHIP_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUEST_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PROJECT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SOURCE_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
SOURCE_VERSION_ID = UUID("99999999-9999-4999-8999-999999999999")
CANDIDATE_ID = UUID("88888888-8888-4888-8888-888888888888")
DERIVED_REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")

QueryRow = dict[str, Any]
QueryResponse = QueryRow | list[QueryRow] | None | Exception


class FakeResult:
    def __init__(self, value: QueryRow | list[QueryRow] | None) -> None:
        self._value = value

    def fetchone(self) -> QueryRow | None:
        if isinstance(self._value, list):
            raise AssertionError("fetchone called for a row list")
        return self._value

    def fetchall(self) -> list[QueryRow]:
        if not isinstance(self._value, list):
            raise AssertionError("fetchall called without a row list")
        return self._value


class RecordingConnection:
    def __init__(self, responses: list[QueryResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object = None) -> FakeResult:
        self.calls.append((" ".join(statement.split()), parameters))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResult(response)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield


def context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(
            user_id=USER_ID,
            role="authenticated",
            session_id=SESSION_ID,
            assurance_level="aal1",
        ),
        company_id=COMPANY_ID,
        membership_id=MEMBERSHIP_ID,
        administrative_role="manager",
        employee_id=None,
    )


def command(
    *,
    project_id: UUID | None = None,
    selected_source_ids: tuple[UUID, ...] = (),
) -> CreatePlanningRequest:
    return CreatePlanningRequest(
        project_id=project_id,
        original_request="Prepare the reviewed operating guide.",
        selected_source_ids=selected_source_ids,
        requested_priority_key="high",
        requested_deadline=None,
        requested_deadline_timezone=None,
        idempotency_key="planning-request-0001",
    )


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[QueryResponse],
) -> RecordingConnection:
    connection = RecordingConnection(responses)

    @contextmanager
    def transaction(*_args: Any, **_kwargs: Any) -> Iterator[RecordingConnection]:
        yield connection

    monkeypatch.setattr(persistence_module, "company_transaction", transaction)
    return connection


def install_role_recording_connection(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[QueryResponse],
) -> tuple[RecordingConnection, list[dict[str, Any]]]:
    connection = RecordingConnection(responses)
    transactions: list[dict[str, Any]] = []

    @contextmanager
    def transaction(*_args: Any, **kwargs: Any) -> Iterator[RecordingConnection]:
        transactions.append(kwargs)
        yield connection

    monkeypatch.setattr(persistence_module, "company_transaction", transaction)
    return connection, transactions


def request_row(*, request_digest: bytes | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": REQUEST_ID,
        "status": "pending_interpretation",
        "request_version": 1,
    }
    if request_digest is not None:
        row["request_digest"] = request_digest
    return row


class IdempotencyUniqueViolation(psycopg.errors.UniqueViolation):
    @property
    def diag(self) -> Any:
        return SimpleNamespace(
            constraint_name=persistence_module.PLANNING_REQUEST_IDEMPOTENCY_CONSTRAINT
        )


def test_create_request_inserts_without_requiring_update_privilege(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = command()
    connection = install_connection(
        monkeypatch,
        [None, None, request_row(request_digest=value.digest)],
    )

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=value
    )

    assert result.created is True
    assert result.request_id == REQUEST_ID
    statement = connection.calls[1][0].lower()
    assert "insert into app.planning_requests" in statement
    assert "on conflict" not in statement
    assert "do update" not in statement


def test_create_request_returns_an_identical_idempotent_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = command()
    connection = install_connection(
        monkeypatch,
        [request_row(request_digest=value.digest)],
    )

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=value
    )

    assert result.created is False
    assert result.request_id == REQUEST_ID
    assert len(connection.calls) == 1
    assert "select id, status, request_version, request_digest" in connection.calls[0][0].lower()


def test_create_request_recovers_a_concurrent_identical_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = command()
    connection = install_connection(
        monkeypatch,
        [
            None,
            IdempotencyUniqueViolation("duplicate idempotency key"),
            request_row(request_digest=value.digest),
        ],
    )

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=value
    )

    assert result.created is False
    assert result.request_id == REQUEST_ID
    assert len(connection.calls) == 3


def test_create_request_pins_sources_without_write_privilege_row_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = command(project_id=PROJECT_ID, selected_source_ids=(SOURCE_ID,))
    connection = install_connection(
        monkeypatch,
        [
            {"id": PROJECT_ID},
            [{"id": SOURCE_ID, "current_version_id": SOURCE_VERSION_ID}],
            None,
            None,
            request_row(request_digest=value.digest),
            None,
        ],
    )

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=value
    )

    assert result.created is True
    assert "for share" not in connection.calls[0][0].lower()
    assert "for share" not in connection.calls[1][0].lower()
    assert "insert into app.planning_request_sources" in connection.calls[5][0].lower()


def test_create_request_rejects_an_idempotency_key_with_different_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = install_connection(
        monkeypatch,
        [request_row(request_digest=b"x" * 32)],
    )

    with pytest.raises(PlanningRequestIdempotencyConflictError):
        PostgresInterpretationStore("postgresql://unused").create_request(
            context=context(), command=command()
        )

    assert len(connection.calls) == 1


def test_submit_clarification_answers_returns_the_derived_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = install_connection(
        monkeypatch,
        [
            {
                "request_id": DERIVED_REQUEST_ID,
                "status": "pending_interpretation",
                "request_version": 2,
                "created": True,
            }
        ],
    )
    value = SubmitClarificationAnswers(
        request_id=REQUEST_ID,
        request_version=1,
        candidate_contract_id=CANDIDATE_ID,
        answers={"task_owner": "The requesting manager approves assignments."},
        idempotency_key="clarification-answer-0001",
        correlation_id=SESSION_ID,
    )

    result = PostgresInterpretationStore("postgresql://unused").submit_clarification_answers(
        context=context(), command=value
    )

    assert result.request_id == DERIVED_REQUEST_ID
    assert result.request_version == 2
    assert result.created is True
    assert "submit_planning_clarifications" in connection.calls[0][0]


def test_projection_uses_recorded_capacity_instead_of_a_false_missing_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    employee_id = UUID("66666666-6666-4666-8666-666666666666")
    install_role_recording_connection(
        monkeypatch,
        [
            {
                "id": REQUEST_ID,
                "original_prompt": "Prepare the guide.",
                "requested_priority_key": None,
                "requested_deadline": None,
                "requested_deadline_timezone": None,
                "request_version": 1,
            },
            [],
            {"count": 0},
            [],
            [
                {
                    "id": employee_id,
                    "timezone": "UTC",
                    "capability_keys": ["technical_review"],
                    "permission_keys": [],
                    "availability_windows": [
                        {
                            "start_at": now + timedelta(hours=1),
                            "end_at": now + timedelta(hours=9),
                        }
                    ],
                    "daily_active_minutes": 360,
                }
            ],
            [],
            [],
        ],
    )

    bundle = PostgresInterpretationStore("postgresql://unused").load_projection(
        context=context(), request_id=REQUEST_ID, retrieval_run_id=SESSION_ID, now=now
    )

    assert len(bundle.projection.capacity) == 1
    assert bundle.projection.capacity[0].employee_id == employee_id
    assert bundle.projection.capacity[0].available_active_minutes == 360
    assert "capacity" not in {marker.kind for marker in bundle.projection.missing_data}


def test_worker_reconciliation_read_uses_only_the_worker_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, transactions = install_role_recording_connection(
        monkeypatch,
        [{"status": "interpreted", "candidate_digest": "ab" * 32}],
    )

    result = PostgresInterpretationStore("postgresql://unused").get_worker_request_state(
        context=context(), request_id=REQUEST_ID
    )

    assert result.status == "interpreted"
    assert result.candidate_digest == "ab" * 32
    assert transactions[0]["role"] == "coordination_worker"
    statement = connection.calls[0][0].lower()
    assert "app.durable_jobs" not in statement
    assert "app.planning_requests" in statement


@pytest.mark.parametrize("project_id", [PROJECT_ID, None])
def test_request_view_returns_saved_intake_and_project_under_the_existing_scope(
    monkeypatch: pytest.MonkeyPatch, project_id: UUID | None
) -> None:
    row: QueryRow = {
        "id": REQUEST_ID,
        "status": "failed",
        "request_version": 1,
        "original_prompt": "Prepare the reviewed operating guide.",
        "project_id": project_id,
        "latest_outcome": "invalid_output",
        "candidate_digest": None,
        "candidate_id": None,
        "snapshot_id": None,
        "plan_id": None,
    }
    for stage in ("interpretation_job", "materialization_job", "planning_job"):
        row[f"{stage}_id"] = None
        row[f"{stage}_state"] = None
    connection, transactions = install_role_recording_connection(monkeypatch, [row])
    selected = replace(context(), demo_run_id=SOURCE_ID, demo_actor_session_id=SOURCE_VERSION_ID)

    result = PostgresInterpretationStore("postgresql://unused").get_request(
        context=selected, request_id=REQUEST_ID
    )

    assert result.original_request == row["original_prompt"]
    assert result.project_id == project_id
    assert connection.calls[0][1] == (COMPANY_ID, REQUEST_ID)
    assert "request.original_prompt, request.project_id" in connection.calls[0][0]
    assert len(connection.calls) == 1
    assert transactions[0]["role"] == "coordination_api"
    assert transactions[0]["actor_id"] == USER_ID
    assert transactions[0]["demo_run_id"] == SOURCE_ID
    assert transactions[0]["demo_actor_session_id"] == SOURCE_VERSION_ID


@pytest.mark.parametrize("state", ["leased", "review_required", "succeeded"])
def test_request_view_projects_the_alto_authoring_job(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    row: QueryRow = {
        "id": REQUEST_ID,
        "status": "interpreted",
        "request_version": 1,
        "original_prompt": "Saved launch request",
        "project_id": PROJECT_ID,
        "latest_outcome": "admitted",
        "candidate_digest": "ab" * 32,
        "candidate_id": CANDIDATE_ID,
        "snapshot_id": SOURCE_ID,
        "plan_id": None,
        "interpretation_job_id": None,
        "interpretation_job_state": None,
        "materialization_job_id": None,
        "materialization_job_state": None,
        "planning_job_id": SESSION_ID,
        "planning_job_state": state,
        "planning_job_kind": "plan.propose",
        "planning_job_attempt_count": 1,
        "planning_job_max_attempts": 3,
        "planning_job_error_code": None,
    }
    connection = install_connection(monkeypatch, [row, [], []])
    result = PostgresInterpretationStore("postgresql://unused").get_request(
        context=context(),
        request_id=REQUEST_ID,
    )
    assert result.planning_job_state == state
    assert result.planning_job is not None
    assert result.planning_job.job_kind == "plan.propose"
    query = connection.calls[0][0]
    assert "value.job_kind in ('plan.propose', 'planning.run')" in query
    assert "value.aggregate_id = snapshot.id" in query
    assert "value.company_id = request.company_id" in query
