from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AuthenticatedUser
from coordination.db.memberships import ActiveMembership

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_A = UUID("11111111-1111-4111-8111-111111111111")
COMPANY_B = UUID("22222222-2222-4222-8222-222222222222")


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
    def __init__(self, membership: ActiveMembership | None) -> None:
        self.membership = membership

    def resolve_active(self, *, user_id: UUID, company_id: UUID) -> ActiveMembership | None:
        assert user_id == USER_ID
        if self.membership is None or company_id != self.membership.company_id:
            return None
        return self.membership


def client_for(membership: ActiveMembership | None) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(
        membership
    )
    return TestClient(application)


def test_session_resolves_role_from_current_membership() -> None:
    membership = ActiveMembership(
        membership_id=uuid4(),
        company_id=COMPANY_A,
        user_id=USER_ID,
        administrative_role="manager",
        employee_id=uuid4(),
    )
    with client_for(membership) as client:
        response = client.get(
            "/v1/session",
            headers={"Authorization": "Bearer valid-token", "X-Company-ID": str(COMPANY_A)},
        )

    assert response.status_code == 200
    assert response.json()["administrative_role"] == "manager"
    assert response.json()["company_id"] == str(COMPANY_A)


def test_cross_company_membership_guess_fails_without_disclosure() -> None:
    membership = ActiveMembership(
        membership_id=uuid4(),
        company_id=COMPANY_A,
        user_id=USER_ID,
        administrative_role="member",
        employee_id=uuid4(),
    )
    with client_for(membership) as client:
        response = client.get(
            "/v1/session",
            headers={"Authorization": "Bearer valid-token", "X-Company-ID": str(COMPANY_B)},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "company was not found"}


def test_session_requires_bearer_and_company_header() -> None:
    with client_for(None) as client:
        missing_bearer = client.get("/v1/session", headers={"X-Company-ID": str(COMPANY_A)})
        missing_company = client.get("/v1/session", headers={"Authorization": "Bearer valid-token"})

    assert missing_bearer.status_code == 401
    assert missing_bearer.headers["www-authenticate"] == "Bearer"
    assert missing_company.status_code == 400
