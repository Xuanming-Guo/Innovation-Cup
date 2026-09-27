"""Existing projects remain readable after the additive ALTO schema upgrade."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from coordination.api.main import create_app
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings, get_settings
from coordination.workspace import persistence
from coordination.workspace.contracts import Project
from coordination.workspace.routes import get_workspace_store, workspace_context


def project_row() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "title": "Existing project",
        "goal_label": None,
        "status": "active",
        "deadline": None,
        "updated_at": datetime(2026, 9, 27, tzinfo=UTC),
        "task_count": 0,
        "completed_task_count": 0,
        "plan_id": None,
        "description": "Preserved project purpose",
    }


@pytest.mark.parametrize("label", [None, "", "Accepted launch"])
def test_project_label_normalizes_only_null(label: str | None) -> None:
    row = {**project_row(), "goal_label": label}
    result = Project.model_validate(row)
    assert result.goal_label == ("" if label is None else label)
    assert row["goal_label"] == label


def test_project_invalid_label_is_not_silently_coerced() -> None:
    with pytest.raises(ValidationError):
        Project.model_validate({**project_row(), "goal_label": {"untrusted": "value"}})


@pytest.mark.parametrize("route", ["home", "projects", "project"])
def test_legacy_project_routes_return_success_with_cors(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    context = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
    )
    row = project_row()
    calls: list[str] = []

    @contextmanager
    def transaction(*args: Any, **kwargs: Any) -> Iterator[Any]:
        assert kwargs["company_id"] == context.company_id
        assert kwargs["actor_id"] == context.actor.user_id
        assert kwargs["role"] == "coordination_api"

        def execute(query: str, parameters: Any) -> Any:
            assert "from app.projects p" in query
            calls.append(query)
            if route == "project":
                assert "p.id=%s" in query
                assert "p.demo_run_id is not distinct from %s" in query
                assert parameters == (context.company_id, row["id"], context.demo_run_id)
                return SimpleNamespace(fetchone=lambda: row)
            assert parameters == (context.company_id, "%%")
            return SimpleNamespace(fetchall=lambda: [row])

        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(persistence, "company_transaction", transaction)
    store = persistence.PostgresWorkspaceStore("postgresql://unused.invalid/unused")
    monkeypatch.setattr(store, "actions", lambda context: [])
    settings_options: dict[str, Any] = {"_env_file": None, "environment": "test"}
    settings = Settings(**settings_options)
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[workspace_context] = lambda: context
    application.dependency_overrides[get_workspace_store] = lambda: store
    suffix = f"projects/{row['id']}" if route == "project" else route
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(
            f"/v1/companies/{context.company_id}/{suffix}",
            headers={"Origin": "http://tauri.localhost"},
        )

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    body = response.json()
    project = (
        body["recent_projects"][0]
        if route == "home"
        else body["projects"][0]
        if route == "projects"
        else body
    )
    assert project["goal_label"] == ""
    assert project["description"] == "Preserved project purpose"
    assert project["id"] == str(row["id"])
    assert len(calls) == 1
    assert row["goal_label"] is None
