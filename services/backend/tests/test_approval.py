from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.approval.contracts import (
    ApprovalDecisionResult,
    ApprovalRequirementView,
    CommitResult,
    ConstraintEvidence,
    PlanBinding,
    PlanEvidence,
    PlanReview,
    PlanTaskView,
    SolverDiagnostic,
)
from coordination.approval.dependencies import get_approval_store
from coordination.approval.persistence import ApprovalStaleError
from coordination.approval.policy import ApprovalRisk, derive_requirements
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser
from coordination.db.memberships import ActiveMembership

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
PLAN_ID = UUID("22222222-2222-4222-8222-222222222222")
REQUEST_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUIREMENT_ID = UUID("44444444-4444-4444-8444-444444444444")


class FakeVerifier:
    def verify(self, token: str) -> AuthenticatedUser:
        assert token == "valid-token"
        return AuthenticatedUser(
            user_id=USER_ID,
            role="authenticated",
            session_id=SESSION_ID,
            assurance_level="aal1",
        )


class FakeMembershipResolver:
    def __init__(self, role: AdministrativeRole) -> None:
        self.role = role

    def resolve_active(self, *, user_id: UUID, company_id: UUID) -> ActiveMembership | None:
        if user_id != USER_ID or company_id != COMPANY_ID:
            return None
        return ActiveMembership(
            membership_id=uuid4(),
            company_id=COMPANY_ID,
            user_id=USER_ID,
            administrative_role=self.role,
            employee_id=uuid4(),
        )


def binding() -> PlanBinding:
    return PlanBinding(
        proposal_digest="11" * 32,
        snapshot_digest="22" * 32,
        source_manifest_digest="33" * 32,
        base_company_revision=7,
        policy_revision=2,
        policy_version="planning-v1",
    )


def review() -> PlanReview:
    start = datetime(2026, 9, 28, 9, tzinfo=UTC)
    return PlanReview(
        plan_id=PLAN_ID,
        request_id=REQUEST_ID,
        request_summary="Prepare a reviewed operating guide.",
        classification="FEASIBLE",
        status="proposed",
        binding=binding(),
        tasks=(
            PlanTaskView(
                task_id=uuid4(),
                task_key="draft",
                title="Draft the guide",
                scheduling_kind="flexible_active",
                start_at=start,
                finish_at=start + timedelta(hours=2),
                owner_resource_id=uuid4(),
            ),
        ),
        changes=(),
        requirements=(
            ApprovalRequirementView(
                requirement_id=REQUIREMENT_ID,
                domain="planning",
                kind="plan_commit",
                authority_kind="company_manager",
                authority_team_id=None,
                reason="Approve the exact proposal.",
                status="pending",
                decided_by_membership_id=None,
                decided_at=None,
                expires_at=None,
            ),
        ),
        can_commit=False,
    )


class FakeApprovalStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.stale_commit = False

    def get_review(self, **values: Any) -> PlanReview:
        self.calls.append(("get_review", values))
        return review()

    def get_evidence(self, **values: Any) -> PlanEvidence:
        self.calls.append(("get_evidence", values))
        return PlanEvidence(
            plan_id=PLAN_ID,
            constraints=(
                ConstraintEvidence(
                    constraint_key="task.draft",
                    family="task_definition",
                    strength="hard",
                    confidentiality="company",
                    source_version_ids=(),
                    authority_refs=("manager:confirmed",),
                ),
            ),
            assumptions=("manager:confirmed",),
            solver=SolverDiagnostic(
                classification="FEASIBLE",
                raw_status="sat",
                termination="completed",
                solver_version="5.1.0.0",
                compiler_version="compiler-v1",
                validator_version="validator-v1",
                runtime_ms=12,
                objective_vector=(),
                diagnostic_constraint_keys=(),
            ),
        )

    def decide(self, **values: Any) -> ApprovalDecisionResult:
        self.calls.append(("decide", values))
        return ApprovalDecisionResult(
            decision_id=uuid4(),
            decision=values["command"].decision,
            replayed=False,
        )

    def commit(self, **values: Any) -> CommitResult:
        self.calls.append(("commit", values))
        if self.stale_commit:
            raise ApprovalStaleError("stale")
        return CommitResult(
            commitment_id=uuid4(), status="committed", company_revision=8, replayed=False
        )


def client_for(role: AdministrativeRole, store: FakeApprovalStore) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(role)
    application.dependency_overrides[get_approval_store] = lambda: store
    return TestClient(application)


def headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer valid-token",
        "X-Company-ID": str(COMPANY_ID),
        "Idempotency-Key": "approval-operation-0001",
    }


def decision_body(*, explanation: str = "") -> dict[str, object]:
    return {
        "requirement_id": str(REQUIREMENT_ID),
        "artifact_digest": "11" * 32,
        "binding": binding().model_dump(mode="json"),
        "explanation": explanation,
        "correlation_id": str(uuid4()),
    }


def test_manager_can_review_exact_plan_and_evidence() -> None:
    store = FakeApprovalStore()
    with client_for("manager", store) as client:
        plan = client.get(f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}", headers=headers())
        evidence = client.get(
            f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}/evidence", headers=headers()
        )

    assert plan.status_code == 200
    assert plan.json()["status"] == "proposed"
    assert plan.json()["can_commit"] is False
    assert evidence.status_code == 200
    assert evidence.json()["solver"]["raw_status"] == "sat"


def test_approval_and_rejection_are_explicit_exact_commands() -> None:
    store = FakeApprovalStore()
    with client_for("company_admin", store) as client:
        approved = client.post(
            f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}/approve",
            headers=headers(),
            json=decision_body(),
        )
        rejected = client.post(
            f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}/reject",
            headers={**headers(), "Idempotency-Key": "approval-operation-0002"},
            json=decision_body(explanation="The deadline authority is missing."),
        )

    assert approved.status_code == 200
    assert approved.json()["decision"] == "approved"
    assert rejected.status_code == 200
    assert rejected.json()["decision"] == "rejected"
    assert store.calls[-1][1]["command"].explanation.startswith("The deadline")


def test_member_cannot_review_or_commit_and_stale_commit_requires_replan() -> None:
    member_store = FakeApprovalStore()
    with client_for("member", member_store) as client:
        forbidden = client.get(
            f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}", headers=headers()
        )
    assert forbidden.status_code == 403
    assert member_store.calls == []

    stale_store = FakeApprovalStore()
    stale_store.stale_commit = True
    with client_for("manager", stale_store) as client:
        stale = client.post(
            f"/v1/companies/{COMPANY_ID}/plans/{PLAN_ID}/commit",
            headers=headers(),
            json={
                "binding": binding().model_dump(mode="json"),
                "correlation_id": str(uuid4()),
            },
        )
    assert stale.status_code == 409
    assert "replan" in stale.json()["detail"]


def test_policy_separates_planning_disclosure_and_affected_team_authority() -> None:
    team_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    team_a = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    requirements = derive_requirements(
        ApprovalRisk(
            deadline_changed=True,
            employee_brief_present=True,
            affected_team_ids=(team_b, team_a, team_b),
        )
    )

    assert [requirement.kind for requirement in requirements] == [
        "plan_commit",
        "deadline_change",
        "cross_team_displacement",
        "cross_team_displacement",
        "employee_brief_disclosure",
    ]
    assert requirements[-1].domain == "disclosure"
    assert requirements[2].team_id == team_a
