from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import get_membership_resolver, get_token_verifier
from coordination.auth.models import AdministrativeRole, AuthenticatedUser
from coordination.db.memberships import ActiveMembership
from coordination.durable.contracts import (
    JobView,
    NotificationPage,
    NotificationView,
    QueueMetrics,
)
from coordination.durable.dependencies import get_durable_store

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
MEMBERSHIP_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
REQUEST_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
JOB_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
NOTIFICATION_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


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
            membership_id=MEMBERSHIP_ID,
            company_id=COMPANY_ID,
            user_id=USER_ID,
            administrative_role=self.role,
            employee_id=None,
        )


def job_view(state: str = "queued") -> JobView:
    return JobView.model_validate(
        {
            "job_id": JOB_ID,
            "job_kind": "interpretation.run",
            "aggregate_id": REQUEST_ID,
            "state": state,
            "attempt_count": 0,
            "max_attempts": 6,
            "available_at": NOW,
            "leased_until": None,
            "cancellation_requested": False,
            "last_error_code": None,
            "created_at": NOW,
            "completed_at": None,
        }
    )


def notification_view() -> NotificationView:
    return NotificationView(
        notification_id=NOTIFICATION_ID,
        message_key="plan_state_changed",
        subject_type="plan",
        subject_id=REQUEST_ID,
        safe_parameters={},
        created_at=NOW,
        delivered_at=NOW,
        seen_at=None,
        acknowledged_at=None,
    )


class FakeDurableStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def ensure_job(self, **values: Any) -> JobView:
        self.calls.append(("ensure_job", values))
        return job_view()

    def get_job(self, **values: Any) -> JobView:
        self.calls.append(("get_job", values))
        return job_view()

    def cancel_job(self, **values: Any) -> JobView:
        self.calls.append(("cancel_job", values))
        return job_view("cancelled")

    def retry_job(self, **values: Any) -> JobView:
        self.calls.append(("retry_job", values))
        return job_view("queued")

    def metrics(self, **values: Any) -> QueueMetrics:
        self.calls.append(("metrics", values))
        return QueueMetrics(
            queued=1,
            leased=0,
            retry_scheduled=0,
            dead_letter=0,
            review_required=0,
            cancelled=0,
            succeeded=0,
            oldest_ready_seconds=2,
            outbox_pending=0,
            notifications_unread=1,
        )

    def list_notifications(self, **values: Any) -> NotificationPage:
        self.calls.append(("list_notifications", values))
        return NotificationPage(notifications=(notification_view(),), next_cursor=None)

    def advance_notification(self, **values: Any) -> NotificationView:
        self.calls.append(("advance_notification", values))
        return notification_view().model_copy(update={"seen_at": NOW})


def client_for(role: AdministrativeRole, store: FakeDurableStore) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_token_verifier] = FakeVerifier
    application.dependency_overrides[get_membership_resolver] = lambda: FakeMembershipResolver(role)
    application.dependency_overrides[get_durable_store] = lambda: store
    return TestClient(application)


def headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    values = {
        "Authorization": "Bearer valid-token",
        "X-Company-ID": str(COMPANY_ID),
    }
    if idempotency_key is not None:
        values["Idempotency-Key"] = idempotency_key
    return values


def test_interpret_endpoint_only_enqueues_durable_work() -> None:
    store = FakeDurableStore()
    with client_for("manager", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{REQUEST_ID}/interpret",
            headers=headers(idempotency_key="interpret-command-0001"),
        )

    assert response.status_code == 202
    assert response.json()["state"] == "queued"
    assert [name for name, _values in store.calls] == ["ensure_job"]
    command = store.calls[0][1]
    assert command["job_kind"] == "interpretation.run"
    assert command["aggregate_id"] == REQUEST_ID


def test_member_cannot_enqueue_or_read_manager_operations() -> None:
    store = FakeDurableStore()
    with client_for("member", store) as client:
        interpret = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{REQUEST_ID}/interpret",
            headers=headers(idempotency_key="interpret-command-0001"),
        )
        metrics = client.get(
            f"/v1/companies/{COMPANY_ID}/operations/metrics",
            headers=headers(),
        )

    assert interpret.status_code == 403
    assert metrics.status_code == 403
    assert store.calls == []


def test_manager_can_retry_a_terminal_side_effect_free_job() -> None:
    store = FakeDurableStore()
    with client_for("manager", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/jobs/{JOB_ID}/retry",
            headers=headers(idempotency_key="retry-command-0001"),
            json={"reason": "Provider configuration was corrected."},
        )

    assert response.status_code == 200
    assert response.json()["state"] == "queued"
    assert [name for name, _values in store.calls] == ["retry_job"]
    command = store.calls[0][1]
    assert command["job_id"] == JOB_ID
    assert command["reason"] == "Provider configuration was corrected."


def test_notifications_are_available_to_members_and_cursor_is_fail_closed() -> None:
    store = FakeDurableStore()
    with client_for("member", store) as client:
        listed = client.get(
            f"/v1/companies/{COMPANY_ID}/me/notifications",
            headers=headers(),
        )
        seen = client.post(
            f"/v1/companies/{COMPANY_ID}/me/notifications/{NOTIFICATION_ID}/seen",
            headers=headers(),
        )
        invalid_cursor = client.get(
            f"/v1/companies/{COMPANY_ID}/me/notifications?cursor=not-a-cursor",
            headers=headers(),
        )

    assert listed.status_code == 200
    assert listed.json()["notifications"][0]["safe_parameters"] == {}
    assert seen.status_code == 200
    assert seen.json()["seen_at"] is not None
    assert invalid_cursor.status_code == 422
    assert [name for name, _values in store.calls] == [
        "list_notifications",
        "advance_notification",
    ]
