from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.planning.northstar import build_northstar_proposal, build_northstar_snapshot
from coordination.workspace.contracts import Project
from coordination.workspace.graph_read import graph, rule_detail
from coordination.workspace.persistence import WorkspaceNotFoundError


def scoped_store(*, role: str = "manager") -> tuple[Any, CompanyContext, UUID, Mock]:
    context = CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1"),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="member",
        employee_id=None,
        demo_run_id=uuid4(),
        demo_actor_session_id=uuid4(),
        demo_planning_authority=role == "manager",
    )
    project_id = uuid4()
    project = Project(
        id=project_id,
        title="Synthetic exact-version review",
        status="planning",
        deadline=None,
        updated_at=datetime.now(UTC),
        task_count=0,
        completed_task_count=0,
        plan_id=uuid4(),
    )
    connection = Mock()

    @contextmanager
    def transaction(selected: CompanyContext, purpose: str) -> Iterator[Mock]:
        assert selected is context
        assert purpose == "workspace:exact-graph"
        yield connection

    store = SimpleNamespace(
        project=Mock(return_value=project),
        workspace=Mock(return_value=SimpleNamespace(viewer=SimpleNamespace(role=role))),
        transaction=transaction,
    )
    return store, context, project_id, connection


@pytest.mark.parametrize("case", ["absent", "legacy", "mismatched_proposal"])
def test_exact_plan_lookup_fails_closed_before_other_graph_reads(case: str) -> None:
    store, context, project_id, connection = scoped_store()
    plan_id = uuid4()
    selected: dict[str, UUID | None] | None = None if case == "absent" else {"ai_proposal_id": None}
    if case == "mismatched_proposal":
        selected = {"ai_proposal_id": uuid4()}
    connection.execute.return_value.fetchone.return_value = selected

    with pytest.raises(WorkspaceNotFoundError, match="exact plan graph was not found"):
        graph(
            store,
            context,
            project_id,
            plan_id=plan_id,
            proposal_id=uuid4() if case == "mismatched_proposal" else None,
        )

    connection.execute.assert_called_once()
    sql, params = connection.execute.call_args.args
    assert "r.project_id=%s" in sql
    assert "r.company_id=p.company_id" in sql
    assert params == (context.company_id, plan_id, project_id, context.demo_run_id)
    store.project.assert_called_once_with(context, project_id, connection=connection)


def test_employee_cannot_use_manager_exact_plan_preview() -> None:
    store, context, project_id, connection = scoped_store(role="employee")
    with pytest.raises(WorkspaceNotFoundError, match="candidate was not found"):
        graph(store, context, project_id, plan_id=uuid4())
    connection.execute.assert_not_called()


def test_exact_plan_graph_keeps_the_selected_candidate_instead_of_the_latest_project_plan() -> None:
    store, context, project_id, connection = scoped_store()
    assert context.demo_run_id is not None
    frozen = build_northstar_snapshot(
        company_id=context.company_id,
        run_id=context.demo_run_id,
        request_id=uuid4(),
        candidate_contract_id=uuid4(),
        source_version_ids={f"LAUNCH-{index:02}": uuid4() for index in range(1, 8)},
        source_manifest_digest="a" * 64,
        base_company_revision=7,
        frozen_at=datetime(2026, 9, 28, tzinfo=UTC),
    )
    proposal = build_northstar_proposal(snapshot=frozen, run_id=context.demo_run_id)
    selected_plan = uuid4()
    candidate = {
        "id": proposal.proposal_id,
        "candidate_payload": {"proposal": proposal.model_dump(mode="json")},
        "candidate_digest": bytes.fromhex(proposal.candidate_digest),
        "plan_id": selected_plan,
        "verification_id": uuid4(),
        "product_status": "CHECKED",
        "passed": False,  # No approval eligibility or external approval-store read.
        "snapshot_id": frozen.snapshot_id,
        "commitment_id": None,
    }
    connection.execute.side_effect = [
        SimpleNamespace(fetchone=lambda: {"ai_proposal_id": proposal.proposal_id}),
        SimpleNamespace(fetchall=lambda: []),
        SimpleNamespace(fetchall=lambda: []),
        SimpleNamespace(fetchone=lambda: candidate),
        SimpleNamespace(fetchall=lambda: []),
        SimpleNamespace(fetchall=lambda: []),
    ]

    result = graph(store, context, project_id, plan_id=selected_plan)

    assert selected_plan != store.project.return_value.plan_id
    assert result.plan_id == selected_plan
    assert result.selected_proposal_id == proposal.proposal_id
    assert len(result.nodes) == len(proposal.draft.tasks)
    assert result.is_candidate_preview
    assert not result.can_approve
    assert not any(node.can_work for node in result.nodes)
    exact_candidate_query = connection.execute.call_args_list[3]
    assert exact_candidate_query.args[1] == (
        context.company_id,
        project_id,
        proposal.proposal_id,
        proposal.proposal_id,
        context.demo_run_id,
    )
    assert connection.execute.call_count == 6
    store.project.assert_called_once_with(context, project_id, connection=connection)
    store.workspace.assert_not_called()


def rule_detail_store(
    context: CompanyContext, connection: Mock
) -> Any:
    @contextmanager
    def transaction(selected: CompanyContext, purpose: str) -> Iterator[Mock]:
        assert selected is context
        assert purpose == "workspace:rule-detail"
        yield connection

    return SimpleNamespace(transaction=transaction)


def test_rule_detail_is_manager_only_and_exactly_bound_to_the_recorded_run() -> None:
    _, context, project_id, connection = scoped_store()
    proposal_id = uuid4()
    result_id = uuid4()
    connection.execute.return_value.fetchone.return_value = {
        "rule_key": "protected.priya.tuesday",
        "encoding_version": "alto-fixed-candidate-compiler.v1",
        "fixed_values": {"technical_expression": "(and (<= 0 1))"},
    }

    result = rule_detail(
        rule_detail_store(context, connection),
        context,
        project_id,
        result_id,
        proposal_id=proposal_id,
    )

    assert result.rule_id == "protected.priya.tuesday"
    assert result.technical_expression == "(and (<= 0 1))"
    sql, params = connection.execute.call_args.args
    assert "request.project_id=%s and proposal.id=%s and result.id=%s" in sql
    assert "verification.demo_run_id is not distinct from %s" in sql
    assert params == (
        context.company_id,
        context.demo_run_id,
        context.demo_run_id,
        context.demo_run_id,
        context.demo_run_id,
        context.demo_run_id,
        project_id,
        proposal_id,
        result_id,
    )


def test_rule_detail_fails_closed_for_employees_and_mismatched_bindings() -> None:
    _, employee, project_id, connection = scoped_store(role="employee")
    with pytest.raises(WorkspaceNotFoundError, match="rule result was not found"):
        rule_detail(
            rule_detail_store(employee, connection),
            employee,
            project_id,
            uuid4(),
            proposal_id=uuid4(),
        )
    connection.execute.assert_not_called()

    _, manager, project_id, connection = scoped_store()
    connection.execute.return_value.fetchone.return_value = None
    with pytest.raises(WorkspaceNotFoundError, match="rule result was not found"):
        rule_detail(
            rule_detail_store(manager, connection),
            manager,
            project_id,
            uuid4(),
            proposal_id=uuid4(),
        )


def test_legacy_rule_detail_reports_missing_raw_assertion_without_inventing_one() -> None:
    _, context, project_id, connection = scoped_store()
    connection.execute.return_value.fetchone.return_value = {
        "rule_key": "protected.priya.tuesday",
        "encoding_version": "legacy-verifier.v1",
        "fixed_values": {},
    }

    result = rule_detail(
        rule_detail_store(context, connection),
        context,
        project_id,
        uuid4(),
        proposal_id=uuid4(),
    )

    assert result.technical_expression is None
    assert result.encoding_version == "legacy-verifier.v1"
