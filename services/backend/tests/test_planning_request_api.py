from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser
from coordination.db.memberships import ActiveMembership
from coordination.interpretation.dependencies import get_interpretation_store
from coordination.interpretation.persistence import (
    ClarificationRecord,
    PlanningRequestRecord,
    PlanningRequestView,
)

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")


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


class FakeStore:
    def __init__(self, *, created: bool = True) -> None:
        self.created = created
        self.commands: list[Any] = []
        self.request_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

    def create_request(self, **values: Any) -> PlanningRequestRecord:
        self.commands.append(values)
        return PlanningRequestRecord(
            request_id=self.request_id,
            status="pending_interpretation",
            request_version=1,
            created=self.created,
        )

    def get_request(self, **values: Any) -> PlanningRequestView:
        self.commands.append(values)
        return PlanningRequestView(
            request_id=self.request_id,
            status="clarification_required",
            request_version=1,
            latest_outcome="clarification_required",
            candidate_digest="ab" * 32,
            clarifications=(
                ClarificationRecord(
                    question_key="task-owner",
                    category="authority",
                    question="Who may own the final review?",
                    blocks_planning=True,
                    status="open",
                ),
            ),
        )


def client_for(role: AdministrativeRole, store: FakeStore) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(role)
    application.dependency_overrides[get_interpretation_store] = lambda: store
    return TestClient(application)


def request_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer valid-token",
        "X-Company-ID": str(COMPANY_ID),
        "Idempotency-Key": "planning-request-0001",
    }


def request_body() -> dict[str, object]:
    return {
        "project_id": None,
        "original_request": "Prepare a reviewed operating guide.",
        "selected_source_ids": [],
        "requested_priority_key": None,
        "requested_deadline": None,
        "requested_deadline_timezone": None,
    }


def test_manager_can_create_idempotent_natural_language_request() -> None:
    store = FakeStore()
    with client_for("manager", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests",
            headers=request_headers(),
            json=request_body(),
        )

    assert response.status_code == 201
    assert response.json()["status"] == "pending_interpretation"
    assert store.commands[0]["command"].original_request.startswith("Prepare")


def test_replayed_request_returns_existing_record_without_duplicate_creation() -> None:
    store = FakeStore(created=False)
    with client_for("company_admin", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests",
            headers=request_headers(),
            json=request_body(),
        )

    assert response.status_code == 200
    assert response.json()["created"] is False


def test_manager_can_read_current_interpretation_state() -> None:
    store = FakeStore()
    with client_for("manager", store) as client:
        response = client.get(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}",
            headers=request_headers(),
        )

    assert response.status_code == 200
    assert response.json() == {
        "request_id": str(store.request_id),
        "status": "clarification_required",
        "request_version": 1,
        "latest_outcome": "clarification_required",
        "candidate_digest": "ab" * 32,
        "candidate_contract_id": None,
        "snapshot_id": None,
        "plan_id": None,
        "interpretation_job_state": None,
        "materialization_job_state": None,
        "planning_job_state": None,
        "interpretation_job": None,
        "materialization_job": None,
        "planning_job": None,
        "clarifications": [
            {
                "question_key": "task-owner",
                "category": "authority",
                "question": "Who may own the final review?",
                "blocks_planning": True,
                "status": "open",
            }
        ],
    }


def test_member_and_cross_company_scope_fail_before_storage() -> None:
    member_store = FakeStore()
    with client_for("member", member_store) as client:
        forbidden = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests",
            headers=request_headers(),
            json=request_body(),
        )
    assert forbidden.status_code == 403
    assert member_store.commands == []

    other_store = FakeStore()
    other_company = UUID("22222222-2222-4222-8222-222222222222")
    with client_for("manager", other_store) as client:
        not_found = client.post(
            f"/v1/companies/{other_company}/planning-requests",
            headers=request_headers(),
            json=request_body(),
        )
    assert not_found.status_code == 404
    assert other_store.commands == []
