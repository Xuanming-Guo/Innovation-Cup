from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

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


class FakeResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class RecordingConnection:
    def __init__(self, responses: list[dict[str, Any] | None]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, object]] = []

    def execute(self, statement: str, parameters: object = None) -> FakeResult:
        self.calls.append((" ".join(statement.split()), parameters))
        return FakeResult(self._responses.pop(0))


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


def command() -> CreatePlanningRequest:
    return CreatePlanningRequest(
        project_id=None,
        original_request="Prepare the reviewed operating guide.",
        selected_source_ids=(),
        requested_priority_key="high",
        requested_deadline=None,
        requested_deadline_timezone=None,
        idempotency_key="planning-request-0001",
    )


def install_connection(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[dict[str, Any] | None],
) -> RecordingConnection:
    connection = RecordingConnection(responses)

    @contextmanager
    def transaction(*_args: Any, **_kwargs: Any) -> Iterator[RecordingConnection]:
        yield connection

    monkeypatch.setattr(persistence_module, "company_transaction", transaction)
    return connection


def request_row(*, request_digest: bytes | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": REQUEST_ID,
        "status": "pending_interpretation",
        "request_version": 1,
    }
    if request_digest is not None:
        row["request_digest"] = request_digest
    return row


def test_create_request_inserts_without_requiring_update_privilege(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = install_connection(monkeypatch, [request_row()])

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=command()
    )

    assert result.created is True
    assert result.request_id == REQUEST_ID
    statement = connection.calls[0][0].lower()
    assert (
        "on conflict (company_id, requester_membership_id, idempotency_key) do nothing"
        in statement
    )
    assert "do update" not in statement


def test_create_request_returns_an_identical_idempotent_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = command()
    connection = install_connection(
        monkeypatch,
        [None, request_row(request_digest=value.digest)],
    )

    result = PostgresInterpretationStore("postgresql://unused").create_request(
        context=context(), command=value
    )

    assert result.created is False
    assert result.request_id == REQUEST_ID
    assert len(connection.calls) == 2
    assert "select id, status, request_version, request_digest" in connection.calls[1][0].lower()


def test_create_request_rejects_an_idempotency_key_with_different_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = install_connection(
        monkeypatch,
        [None, request_row(request_digest=b"x" * 32)],
    )

    with pytest.raises(PlanningRequestIdempotencyConflictError):
        PostgresInterpretationStore("postgresql://unused").create_request(
            context=context(), command=command()
        )

    assert len(connection.calls) == 2
