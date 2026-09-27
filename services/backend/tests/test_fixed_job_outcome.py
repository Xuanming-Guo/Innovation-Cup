from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.durable import handlers
from coordination.durable.runner import PermanentJobError
from coordination.planning.authoring import AuthoringOutcome
from coordination.planning.contracts import PlanningSnapshot
from coordination.planning.fixed_contracts import MAX_FIXED_PLAN_PROPOSALS
from coordination.planning.fixed_verifier import verify_fixed_candidate
from coordination.planning.northstar import (
    build_northstar_proposal,
    build_northstar_snapshot,
)

COMPANY = UUID("11111111-0000-4111-8111-111111111111")
RUN = UUID("22222222-0000-4222-8222-222222222222")


def locked_northstar_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Mock, Mock, PlanningSnapshot]:
    snapshot = build_northstar_snapshot(
        company_id=COMPANY,
        run_id=RUN,
        request_id=uuid4(),
        candidate_contract_id=uuid4(),
        source_version_ids={f"LAUNCH-{index:02}": UUID(int=index) for index in range(1, 8)},
        source_manifest_digest="a" * 64,
        base_company_revision=7,
        frozen_at=datetime(2026, 9, 28, tzinfo=ZoneInfo("America/Los_Angeles")),
    )
    context = CompanyContext(
        actor=AuthenticatedUser(
            user_id=uuid4(), role="authenticated", session_id=uuid4(), assurance_level="aal1"
        ),
        company_id=COMPANY,
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=RUN,
    )
    lease = Mock(
        payload={"snapshot_id": str(snapshot.snapshot_id)},
        attempt_count=1,
        job_id=uuid4(),
        lease_token=uuid4(),
    )
    lease.company_context.return_value = context
    ledger = Mock()
    ledger.history.return_value = ()
    ledger.save_authored_result.side_effect = (
        lambda *, result, **_: result.proposal.proposal_id if result.approvable else None
    )
    snapshot_store = Mock()
    snapshot_store.load_snapshot.return_value = snapshot
    monkeypatch.setattr(handlers, "_assert_planning_lease", Mock())
    monkeypatch.setattr(handlers, "load_run_mode", Mock(return_value="live"))
    monkeypatch.setattr(handlers, "PostgresFixedCandidateLedger", Mock(return_value=ledger))
    monkeypatch.setattr(handlers, "PostgresPlanningLedger", Mock(return_value=snapshot_store))
    monkeypatch.setattr(handlers, "CompanyGeminiGatewayFactory", Mock())
    return lease, ledger, snapshot


@pytest.mark.parametrize(
    "status,has_plan",
    [
        ("CHECKED", True),
        ("CHECKED", False),
        ("UNABLE_TO_VERIFY", False),
        ("VIOLATIONS_FOUND", False),
    ],
)
def test_fixed_job_only_succeeds_with_a_verified_reviewable_plan(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    has_plan: bool,
) -> None:
    snapshot_id, plan_id = uuid4(), uuid4() if has_plan else None
    lease = Mock(payload={"snapshot_id": str(snapshot_id)}, attempt_count=1)
    monkeypatch.setattr(handlers, "_assert_planning_lease", Mock())
    monkeypatch.setattr(handlers, "load_run_mode", Mock(return_value="live"))
    monkeypatch.setattr(handlers, "PostgresFixedCandidateLedger", Mock())
    monkeypatch.setattr(handlers, "PostgresPlanningLedger", Mock())
    factory = Mock()
    monkeypatch.setattr(handlers, "CompanyGeminiGatewayFactory", factory)
    outcome = AuthoringOutcome(status, plan_id, None, 0, 3, "bounded_result")
    run = Mock(return_value=outcome)
    service = Mock(return_value=SimpleNamespace(run=run))
    monkeypatch.setattr(handlers, "FixedCandidatePlanningService", service)
    handler = handlers.FixedPlanningJobHandler(
        Settings(database_url=SecretStr("postgresql://unused")),
    )
    if status == "CHECKED" and has_plan:
        result = handler(lease)
        assert result.values["classification"] == "CHECKED"
        assert result.values["plan_id"] == str(plan_id)
    else:
        with pytest.raises(PermanentJobError, match="fixed_plan_not_verified"):
            handler(lease)
    run.assert_called_once()
    assert factory.call_args.kwargs["for_planning"] is True
    assert service.call_args.kwargs["max_proposals"] == MAX_FIXED_PLAN_PROPOSALS


def test_locked_northstar_uses_verified_p1_without_calling_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease, ledger, snapshot = locked_northstar_fixture(monkeypatch)
    failed_proposal = build_northstar_proposal(
        snapshot=snapshot, run_id=RUN, variant="D0"
    ).model_copy(update={"author_kind": "ai_authored"})
    failed = verify_fixed_candidate(snapshot, failed_proposal)
    ledger.history.return_value = (failed,)
    service = Mock()
    monkeypatch.setattr(handlers, "FixedCandidatePlanningService", service)

    result = handlers.FixedPlanningJobHandler(
        Settings(database_url=SecretStr("postgresql://unused"), hackathon_demo=True),
    )(lease)

    assert result.values["classification"] == "CHECKED"
    assert result.values["author_kind"] == "authored_replay"
    assert result.values["independent_validation_passed"] is True
    assert result.values["proposal_count"] == 2
    assert result.values["model_rounds"] == 0
    assert result.values["reason"] == "northstar_demo_verified_schedule"
    service.assert_not_called()
    saved = ledger.save_authored_result.call_args.kwargs["result"]
    assert saved.approvable is True
    assert saved.proposal.author_kind == "authored_replay"
    assert saved.proposal.version == 2
    assert saved.proposal.parent_proposal_id == failed.proposal.proposal_id


def test_locked_northstar_fresh_request_uses_verified_p1_without_provider_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease, ledger, _ = locked_northstar_fixture(monkeypatch)
    service = Mock()
    monkeypatch.setattr(handlers, "FixedCandidatePlanningService", service)

    result = handlers.FixedPlanningJobHandler(
        Settings(database_url=SecretStr("postgresql://unused"), hackathon_demo=True),
    )(lease)

    assert result.values["classification"] == "CHECKED"
    assert result.values["author_kind"] == "authored_replay"
    assert result.values["model_rounds"] == 0
    assert ledger.admitted_context.call_count == 1
    assert ledger.save_authored_result.call_args.kwargs["result"].approvable
    service.assert_not_called()


def test_locked_northstar_never_promotes_an_unverified_pinned_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lease, ledger, _ = locked_northstar_fixture(monkeypatch)
    service = Mock()
    monkeypatch.setattr(handlers, "FixedCandidatePlanningService", service)
    failed = SimpleNamespace(
        approvable=False,
        proposal=SimpleNamespace(candidate_digest="b" * 64),
        check=SimpleNamespace(product_status="VIOLATIONS_FOUND"),
        validation=None,
    )
    monkeypatch.setattr(handlers, "verify_fixed_candidate", Mock(return_value=failed))
    ledger.save_authored_result.return_value = None

    with pytest.raises(PermanentJobError, match="fixed_plan_not_verified"):
        handlers.FixedPlanningJobHandler(
            Settings(database_url=SecretStr("postgresql://unused"), hackathon_demo=True),
        )(lease)
    service.assert_not_called()
