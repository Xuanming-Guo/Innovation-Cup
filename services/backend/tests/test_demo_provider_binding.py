from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest

from coordination.ai_provider import persistence
from coordination.ai_provider.persistence import (
    AiProviderAuthorityError,
    AiProviderStoreUnavailableError,
    PostgresAiProviderStore,
)
from coordination.auth.models import AuthenticatedUser, CompanyContext


def context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="member",
        employee_id=None,
        demo_run_id=uuid4(),
        demo_actor_session_id=uuid4(),
    )


@pytest.mark.parametrize(
    "binding,row_exists",
    [
        pytest.param(None, True, id="sql-null-before-first-profile"),
        pytest.param(None, False, id="absent-row"),
        pytest.param(
            {
                "profile_id": str(uuid4()),
                "current_profile_version_id": str(uuid4()),
                "latest_profile_version_id": str(uuid4()),
                "version": 2,
                "credential_hint": "0123456789ab",
                "provider": "vertex_ai",
                "status": "configured",
            },
            True,
            id="existing-bound-profile",
        ),
    ],
)
def test_demo_binding_handles_empty_and_existing_profiles(
    monkeypatch: pytest.MonkeyPatch,
    binding: dict[str, object] | None,
    row_exists: bool,
) -> None:
    selected = context()
    transaction = MagicMock()
    connection = transaction.return_value.__enter__.return_value
    connection.execute.return_value.fetchone.return_value = (
        {"value": binding} if row_exists else None
    )
    monkeypatch.setattr(persistence, "company_transaction", transaction)

    result = PostgresAiProviderStore(
        "postgresql://unused", connect_timeout_seconds=7
    ).get_demo_binding(context=selected)

    assert result == (binding if binding is not None else {})
    assert result is not binding
    transaction.assert_called_once_with(
        "postgresql://unused",
        role="coordination_api",
        actor_id=selected.actor.user_id,
        company_id=selected.company_id,
        demo_run_id=selected.demo_run_id,
        demo_actor_session_id=selected.demo_actor_session_id,
        purpose="ai_provider.demo.binding",
        connect_timeout_seconds=7,
    )
    connection.execute.assert_called_once_with("select app.get_demo_provider_binding() as value")


def test_demo_binding_requires_selected_run_before_opening_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = MagicMock()
    monkeypatch.setattr(persistence, "company_transaction", transaction)

    with pytest.raises(AiProviderAuthorityError, match="select an owned run"):
        PostgresAiProviderStore("postgresql://unused").get_demo_binding(
            context=replace(context(), demo_run_id=None, demo_actor_session_id=None)
        )

    transaction.assert_not_called()


def test_demo_binding_does_not_treat_database_failure_as_an_empty_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = MagicMock()
    connection = transaction.return_value.__enter__.return_value
    error = psycopg.OperationalError("synthetic connection failure")
    connection.execute.side_effect = error
    monkeypatch.setattr(persistence, "company_transaction", transaction)

    with pytest.raises(AiProviderStoreUnavailableError) as caught:
        PostgresAiProviderStore("postgresql://unused").get_demo_binding(context=context())

    assert caught.value.__cause__ is error
