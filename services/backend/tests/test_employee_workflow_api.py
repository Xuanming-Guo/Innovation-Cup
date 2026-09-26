from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser
from coordination.db.memberships import ActiveMembership
from coordination.employee.contracts import (
    ApprovedBrief,
    EmployeeTask,
    ReviewPolicyResult,
    ReviewResult,
    SubmissionResult,
    SubmissionReviewView,
    TaskTransitionResult,
)
from coordination.employee.dependencies import get_employee_store
from coordination.employee.persistence import EmployeeStateConflictError

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
EMPLOYEE_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
TASK_ID = UUID("22222222-2222-4222-8222-222222222222")
SUBMISSION_ID = UUID("33333333-3333-4333-8333-333333333333")


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
            employee_id=EMPLOYEE_ID,
        )


class FakeEmployeeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_transition = False

    def list_tasks(self, **values: Any) -> tuple[EmployeeTask, ...]:
        self.calls.append(("list_tasks", values))
        start = datetime(2026, 9, 28, 9, tzinfo=UTC)
        return (
            EmployeeTask(
                task_id=TASK_ID,
                task_key="publish-guide",
                title="Publish the operating guide",
                scheduling_kind="flexible_active",
                status="assigned",
                row_version=4,
                start_at=start,
                finish_at=start + timedelta(hours=2),
                reviewer_name="Mina Reviewer",
                latest_submission_id=None,
                latest_submission_version=None,
                approved_brief=ApprovedBrief(
                    brief_version_id=uuid4(),
                    version=2,
                    content={
                        "purpose": "Give operators a reviewed procedure.",
                        "deliverable": "One accessible operating guide.",
                    },
                ),
            ),
        )

    def transition(self, **values: Any) -> TaskTransitionResult:
        self.calls.append(("transition", values))
        if self.fail_transition:
            raise EmployeeStateConflictError("stale")
        return TaskTransitionResult(
            event_id=uuid4(), task_status="acknowledged", task_version=5, replayed=False
        )

    def set_review_policy(self, **values: Any) -> ReviewPolicyResult:
        self.calls.append(("set_review_policy", values))
        return ReviewPolicyResult(policy_id=uuid4(), version=1, task_version=5, replayed=False)

    def submit(self, **values: Any) -> SubmissionResult:
        self.calls.append(("submit", values))
        return SubmissionResult(
            submission_id=SUBMISSION_ID,
            version=1,
            state="submitted",
            task_version=8,
            replayed=False,
        )

    def get_submission(self, **values: Any) -> SubmissionReviewView:
        self.calls.append(("get_submission", values))
        return SubmissionReviewView(
            submission_id=SUBMISSION_ID,
            task_id=TASK_ID,
            task_title="Publish the operating guide",
            version=1,
            state="submitted",
            narrative="Reviewed guide is ready.",
            external_evidence_refs=("ticket:OPS-42",),
            submission_digest="ab" * 32,
            submitting_employee_id=EMPLOYEE_ID,
            submitting_employee_name="Alex Operator",
            review_policy_version=1,
            submitted_at=datetime(2026, 9, 28, 11, tzinfo=UTC),
            files=(),
        )

    def review(self, **values: Any) -> ReviewResult:
        self.calls.append(("review", values))
        return ReviewResult(
            review_id=uuid4(),
            decision=values["command"].decision,
            task_status=values["command"].decision,
            task_version=9,
            replayed=False,
        )


def client_for(role: AdministrativeRole, store: FakeEmployeeStore) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(role)
    application.dependency_overrides[get_employee_store] = lambda: store
    return TestClient(application)


def headers(*, idempotency_key: str = "employee-command-0001") -> dict[str, str]:
    return {
        "Authorization": "Bearer valid-token",
        "X-Company-ID": str(COMPANY_ID),
        "Idempotency-Key": idempotency_key,
    }


def test_employee_task_view_contains_only_task_facts_and_approved_brief() -> None:
    store = FakeEmployeeStore()
    with client_for("member", store) as client:
        response = client.get(f"/v1/companies/{COMPANY_ID}/me/tasks?view=today", headers=headers())

    assert response.status_code == 200
    body = response.json()
    assert body["view"] == "today"
    assert body["tasks"][0]["title"] == "Publish the operating guide"
    assert body["tasks"][0]["approved_brief"]["content"]["purpose"].startswith("Give")
    assert "constraint_evidence" not in body["tasks"][0]
    assert store.calls[0][1]["view"] == "today"


def test_employee_transition_binds_exact_version_and_idempotency_key() -> None:
    store = FakeEmployeeStore()
    with client_for("member", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/events",
            headers=headers(),
            json={
                "command": "acknowledge",
                "expected_task_version": 4,
                "payload": {},
                "correlation_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    assert response.json()["task_status"] == "acknowledged"
    command = store.calls[0][1]["command"]
    assert command.expected_task_version == 4
    assert command.idempotency_key == "employee-command-0001"


def test_manager_sets_reviewer_and_member_cannot_change_policy() -> None:
    store = FakeEmployeeStore()
    body = {
        "reviewer_employee_id": str(EMPLOYEE_ID),
        "self_certifiable": False,
        "self_certification_rule": "",
        "expected_task_version": 4,
        "correlation_id": str(uuid4()),
    }
    with client_for("manager", store) as client:
        allowed = client.put(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/review-policy",
            headers=headers(),
            json=body,
        )
    assert allowed.status_code == 200
    assert allowed.json()["version"] == 1

    member_store = FakeEmployeeStore()
    with client_for("member", member_store) as client:
        forbidden = client.put(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/review-policy",
            headers=headers(),
            json=body,
        )
    assert forbidden.status_code == 403
    assert member_store.calls == []


def test_submission_and_exact_review_are_forwarded_as_typed_commands() -> None:
    store = FakeEmployeeStore()
    with client_for("member", store) as client:
        submitted = client.post(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/submissions",
            headers=headers(idempotency_key="employee-submit-0001"),
            json={
                "narrative": "Reviewed guide is ready.",
                "external_evidence_refs": ["ticket:OPS-42"],
                "file_ids": [],
                "reported_active_minutes": 55,
                "expected_task_version": 7,
                "correlation_id": str(uuid4()),
            },
        )
        review_view = client.get(
            f"/v1/companies/{COMPANY_ID}/submissions/{SUBMISSION_ID}",
            headers=headers(),
        )
        reviewed = client.post(
            f"/v1/companies/{COMPANY_ID}/submissions/{SUBMISSION_ID}/review",
            headers=headers(idempotency_key="employee-review-0001"),
            json={
                "expected_submission_version": 1,
                "submission_digest": "ab" * 32,
                "decision": "accepted",
                "criterion_findings": [{"criterion": "complete", "passed": True}],
                "correction_request": "",
                "correlation_id": str(uuid4()),
            },
        )

    assert submitted.status_code == 201
    assert submitted.json()["submission_id"] == str(SUBMISSION_ID)
    assert review_view.status_code == 200
    assert review_view.json()["submission_digest"] == "ab" * 32
    assert reviewed.status_code == 200
    assert reviewed.json()["decision"] == "accepted"
    assert store.calls[0][1]["command"].submission_digest
    assert store.calls[2][1]["command"].submission_digest == "ab" * 32


def test_invalid_or_stale_commands_fail_before_or_at_the_store_boundary() -> None:
    store = FakeEmployeeStore()
    with client_for("member", store) as client:
        invalid = client.post(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/submissions",
            headers=headers(),
            json={
                "narrative": "Evidence",
                "external_evidence_refs": [],
                "file_ids": [str(SUBMISSION_ID), str(SUBMISSION_ID)],
                "reported_active_minutes": None,
                "expected_task_version": 2,
                "correlation_id": str(uuid4()),
            },
        )
    assert invalid.status_code == 422
    assert store.calls == []

    store.fail_transition = True
    with client_for("member", store) as client:
        stale = client.post(
            f"/v1/companies/{COMPANY_ID}/tasks/{TASK_ID}/events",
            headers=headers(),
            json={
                "command": "start",
                "expected_task_version": 2,
                "payload": {},
                "correlation_id": str(uuid4()),
            },
        )
    assert stale.status_code == 409


def test_cross_company_task_access_is_hidden_before_storage() -> None:
    store = FakeEmployeeStore()
    other_company = UUID("99999999-9999-4999-8999-999999999999")
    with client_for("member", store) as client:
        response = client.get(
            f"/v1/companies/{other_company}/me/tasks?view=today", headers=headers()
        )

    assert response.status_code == 404
    assert store.calls == []
