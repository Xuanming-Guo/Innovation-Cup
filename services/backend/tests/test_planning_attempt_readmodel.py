from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4, uuid5

import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.interpretation import persistence
from coordination.interpretation.persistence import PostgresInterpretationStore
from coordination.planning.fixed_contracts import MAX_FIXED_PLAN_PROPOSALS


def selected_request(
    monkeypatch: pytest.MonkeyPatch,
    model_rows: list[dict[str, Any]],
    *,
    run_id: UUID | None,
    kind: str = "plan.propose",
) -> tuple[CompanyContext, UUID, UUID, Mock, list[dict[str, Any]]]:
    context = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=run_id,
        demo_actor_session_id=uuid4() if run_id else None,
        demo_planning_authority=bool(run_id),
    )
    request_id, job_id = uuid4(), uuid4()
    row = {
        "id": request_id,
        "status": "interpreted",
        "request_version": 1,
        "original_prompt": "Approved planning request",
        "project_id": uuid4(),
        "latest_outcome": "admitted",
        "candidate_digest": "ab" * 32,
        "candidate_id": uuid4(),
        "snapshot_id": uuid4(),
        "plan_id": None,
        "interpretation_job_id": None,
        "interpretation_job_state": "succeeded",
        "materialization_job_id": None,
        "materialization_job_state": "succeeded",
        "planning_job_id": job_id,
        "planning_job_state": "review_required",
        "planning_job_kind": kind,
        "planning_job_attempt_count": 1,
        "planning_job_max_attempts": 3,
        "planning_job_error_code": "fixed_plan_not_verified",
    }
    connection = Mock()
    responses = [Mock(fetchone=Mock(return_value=row)), Mock(fetchall=Mock(return_value=[]))]
    if kind == "plan.propose":
        responses.append(Mock(fetchall=Mock(return_value=model_rows)))
    connection.execute.side_effect = responses
    transactions: list[dict[str, Any]] = []

    @contextmanager
    def transaction(*_args: Any, **kwargs: Any) -> Iterator[Mock]:
        transactions.append(kwargs)
        yield connection

    monkeypatch.setattr(persistence, "company_transaction", transaction)
    return context, request_id, job_id, connection, transactions


@pytest.mark.parametrize("run_id", [None, UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")])
def test_model_attempts_are_bound_to_the_exact_planning_workflow_and_scope(
    monkeypatch: pytest.MonkeyPatch, run_id: UUID | None
) -> None:
    selected, request_id, job_id, connection, transactions = selected_request(
        monkeypatch,
        [
            {"status": "failed", "error_code": "model_output_truncated"},
            {"status": "succeeded", "error_code": None},
            {"status": "succeeded", "error_code": None},
        ],
        run_id=run_id,
    )

    result = PostgresInterpretationStore("postgresql://unused").get_request(
        context=selected, request_id=request_id
    )

    assert result.planning_job is not None
    assert result.planning_job.attempt_count == 1
    assert result.planning_job.model_call_count == 3
    assert result.planning_job.latest_model_error_code == "model_output_truncated"
    assert transactions[0]["role"] == "coordination_api"
    assert transactions[0]["actor_id"] == selected.actor.user_id
    assert transactions[0]["company_id"] == selected.company_id
    assert transactions[0]["demo_run_id"] == run_id
    assert transactions[0]["demo_actor_session_id"] == selected.demo_actor_session_id
    sql, params = connection.execute.call_args.args
    assert "model.company_id = %s and model.request_id = %s" in sql
    assert "model.demo_run_id is not distinct from %s" in sql
    assert "model.id = any(%s::uuid[])" in sql
    assert "model.stage in ('plan.propose', 'plan.revise')" in sql
    assert "order by model.started_at desc, model.id desc" in sql
    assert params[:3] == (selected.company_id, request_id, run_id)
    assert set(params[3]) == {
        uuid5(job_id, f"author:{round_index}:attempt:{attempt}")
        for round_index in range(1, MAX_FIXED_PLAN_PROPOSALS + 1)
        for attempt in range(1, 21)
    }
    assert "candidate_payload" not in sql
    assert "usage" not in sql
    assert all(
        call.args[0].lstrip().lower().startswith("select")
        for call in connection.execute.call_args_list
    )


@pytest.mark.parametrize(
    "rows,expected_count,expected_code",
    [
        ([], 0, None),
        ([{"status": "failed", "error_code": "private provider detail must not escape"}], 1, None),
        (
            [{"status": "failed", "error_code": "prior_work_version_changed"}],
            1,
            "prior_work_version_changed",
        ),
        (
            [
                {"status": "succeeded", "error_code": None},
                {"status": "failed", "error_code": "model_output_truncated"},
            ],
            2,
            None,
        ),
        ([{"status": "running", "error_code": None}], 1, None),
    ],
)
def test_latest_attempt_metadata_is_safe_and_does_not_reuse_an_older_failure(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, Any]],
    expected_count: int,
    expected_code: str | None,
) -> None:
    selected, request_id, _, _, _ = selected_request(monkeypatch, rows, run_id=None)
    result = PostgresInterpretationStore("postgresql://unused").get_request(
        context=selected, request_id=request_id
    )
    assert result.planning_job is not None
    assert result.planning_job.model_call_count == expected_count
    assert result.planning_job.latest_model_error_code == expected_code


def test_legacy_planner_has_no_invented_model_count_or_model_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected, request_id, _, connection, _ = selected_request(
        monkeypatch, [], run_id=None, kind="planning.run"
    )
    result = PostgresInterpretationStore("postgresql://unused").get_request(
        context=selected, request_id=request_id
    )
    assert result.planning_job is not None
    assert result.planning_job.model_call_count is None
    assert result.planning_job.latest_model_error_code is None
    assert connection.execute.call_count == 2
    assert all("app.model_runs" not in call.args[0] for call in connection.execute.call_args_list)
