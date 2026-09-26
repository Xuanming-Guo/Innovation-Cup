from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
)

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MEMBERSHIP_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUEST_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PROJECT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SOURCE_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
SOURCE_VERSION_ID = UUID("99999999-9999-4999-8999-999999999999")

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


def test_worker_reconciliation_read_uses_only_the_worker_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection, transactions = install_role_recording_connection(
        monkeypatch,
        [{"status": "interpreted", "candidate_digest": "ab" * 32}],
    )

    result = PostgresInterpretationStore(
        "postgresql://unused"
    ).get_worker_request_state(context=context(), request_id=REQUEST_ID)

    assert result.status == "interpreted"
    assert result.candidate_digest == "ab" * 32
    assert transactions[0]["role"] == "coordination_worker"
    statement = connection.calls[0][0].lower()
    assert "app.durable_jobs" not in statement
    assert "app.planning_requests" in statement
