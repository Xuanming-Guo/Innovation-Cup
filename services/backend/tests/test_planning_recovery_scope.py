from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import require_company_context
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.durable import persistence as durable_persistence
from coordination.durable.persistence import JobNotFoundError, PostgresDurableStore
from coordination.interpretation.dependencies import get_interpretation_store
from coordination.interpretation.persistence import PlanningRequestView, PlanningStageJob
from coordination.planning.northstar import NORTHSTAR_INTAKE


def selected_context(*, run_id: UUID | None) -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=run_id,
        demo_actor_session_id=uuid4() if run_id else None,
        demo_planning_authority=run_id is not None,
    )


@pytest.mark.parametrize("demo", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_retry_preflight_requires_the_exact_visible_scope_before_definer_call(
    monkeypatch: pytest.MonkeyPatch, demo: bool, visible: bool
) -> None:
    context = selected_context(run_id=uuid4() if demo else None)
    job_id = uuid4()
    now = datetime.now(UTC)
    job = {
        "job_id": job_id,
        "job_kind": "interpretation.run",
        "aggregate_id": uuid4(),
        "state": "queued",
        "attempt_count": 1,
        "max_attempts": 6,
        "available_at": now,
        "leased_until": None,
        "cancellation_requested": False,
        "last_error_code": None,
        "created_at": now,
        "completed_at": None,
    }
    connection = Mock()
    connection.execute.side_effect = [
        SimpleNamespace(fetchone=lambda: {"id": job_id} if visible else None),
        SimpleNamespace(fetchone=lambda: job),
    ]
    scopes: list[dict[str, Any]] = []

    @contextmanager
    def transaction(*_args: Any, **kwargs: Any) -> Iterator[Mock]:
        scopes.append(kwargs)
        yield connection

    monkeypatch.setattr(durable_persistence, "company_transaction", transaction)

    def retry() -> Any:
        return PostgresDurableStore("postgresql://unused").retry_job(
            context=context,
            job_id=job_id,
            reason="Operator corrected provider configuration.",
            idempotency_key="same-explicit-retry-key",
            command_digest=b"r" * 32,
        )

    if visible:
        assert retry().job_id == job_id
        assert connection.execute.call_count == 2
        assert "app.retry_durable_planning_job" in connection.execute.call_args_list[1].args[0]
    else:
        with pytest.raises(JobNotFoundError, match="job was not found"):
            retry()
        assert connection.execute.call_count == 1
    sql, params = connection.execute.call_args_list[0].args
    assert "demo_run_id is not distinct from %s::uuid" in sql
    assert params == (context.company_id, job_id, context.demo_run_id)
    assert scopes[0]["role"] == "coordination_api"
    assert scopes[0]["actor_id"] == context.actor.user_id
    assert scopes[0]["demo_run_id"] == context.demo_run_id
    assert scopes[0]["demo_actor_session_id"] == context.demo_actor_session_id


@pytest.mark.parametrize(
    ("state", "attempts", "expected"),
    [
        ("review_required", 1, True),
        ("dead_letter", 19, True),
        ("review_required", 20, False),
        ("dead_letter", 20, False),
        ("queued", 1, False),
        ("leased", 1, False),
        ("succeeded", 1, False),
        ("cancelled", 1, False),
    ],
)
def test_request_api_retry_hint_obeys_terminal_state_and_total_attempt_bound(
    state: str, attempts: int, expected: bool
) -> None:
    context = selected_context(run_id=uuid4())
    store = Mock()
    job = PlanningStageJob(uuid4(), state, attempts, 20, "model_invalid_output")
    view = PlanningRequestView(
        request_id=uuid4(),
        status="failed",
        request_version=1,
        latest_outcome="invalid_output",
        candidate_digest=None,
        clarifications=(),
        original_request=NORTHSTAR_INTAKE,
        project_id=uuid4(),
        interpretation_job=job,
        materialization_job=job,
        planning_job=job,
    )
    store.get_request.return_value = view
    application = create_app()
    application.dependency_overrides[require_company_context] = lambda: context
    application.dependency_overrides[get_interpretation_store] = lambda: store
    with TestClient(application) as client:
        response = client.get(
            f"/v1/companies/{context.company_id}/planning-requests/{view.request_id}"
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["original_request"] == view.original_request
    assert payload["project_id"] == str(view.project_id)
    assert payload["interpretation_job"]["can_retry"] is (expected and attempts < 3)
    for stage in ("materialization_job", "planning_job"):
        assert payload[stage]["can_retry"] is expected
    store.get_request.assert_called_once_with(context=context, request_id=view.request_id)


@pytest.mark.parametrize("demo", [False, True])
def test_request_api_never_offers_manager_recovery_without_current_planning_authority(
    demo: bool,
) -> None:
    context = selected_context(run_id=uuid4() if demo else None)
    # Real manager membership must not override an employee demo actor selection.
    context = replace(
        context,
        administrative_role="manager" if demo else "member",
        demo_planning_authority=False,
    )
    store = Mock()
    application = create_app()
    application.dependency_overrides[require_company_context] = lambda: context
    application.dependency_overrides[get_interpretation_store] = lambda: store
    with TestClient(application) as client:
        response = client.get(f"/v1/companies/{context.company_id}/planning-requests/{uuid4()}")
    assert response.status_code == 403
    store.get_request.assert_not_called()
