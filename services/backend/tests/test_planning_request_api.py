from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from coordination.api.main import create_app, get_demo_intake_store
from coordination.auth.dependencies import (
    get_membership_resolver,
    get_token_verifier,
    require_company_context,
)
from coordination.auth.models import AdministrativeRole, AuthenticatedUser, CompanyContext
from coordination.db.memberships import ActiveMembership
from coordination.durable.contracts import JobView
from coordination.durable.dependencies import get_durable_store
from coordination.interpretation.dependencies import get_interpretation_store
from coordination.interpretation.persistence import (
    ClarificationRecord,
    PlanningRequestRecord,
    PlanningRequestView,
    PlanningStageJob,
)
from coordination.planning.northstar import NORTHSTAR_INTAKE

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
        self.derived_request_id = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")

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

    def submit_clarification_answers(self, **values: Any) -> PlanningRequestRecord:
        self.commands.append(values)
        return PlanningRequestRecord(
            request_id=self.derived_request_id,
            status="pending_interpretation",
            request_version=2,
            created=self.created,
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
        "original_request": "",
        "project_id": None,
        "intake_supported": True,
        "intake_limitation": None,
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


def test_manager_can_answer_blocking_clarifications_as_a_derived_request() -> None:
    store = FakeStore()
    candidate_id = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    with client_for("manager", store) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}/clarifications",
            headers={**request_headers(), "Idempotency-Key": "clarification-answer-0001"},
            json={
                "request_version": 1,
                "candidate_contract_id": str(candidate_id),
                "answers": {"task-owner": "The requesting manager holds approval authority."},
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "request_id": str(store.derived_request_id),
        "status": "pending_interpretation",
        "request_version": 2,
        "created": True,
    }
    command = store.commands[0]["command"]
    assert command.request_id == store.request_id
    assert command.candidate_contract_id == candidate_id
    assert command.answers == {"task-owner": "The requesting manager holds approval authority."}


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


class DemoIntakeStore(FakeStore):
    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def get_request(self, **values: Any) -> PlanningRequestView:
        return replace(
            super().get_request(**values),
            original_request=self.prompt,
            interpretation_job_state="review_required",
            interpretation_job=PlanningStageJob(
                job_id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
                state="review_required",
                attempt_count=1,
                max_attempts=6,
                last_error_code="model_invalid_output",
            ),
        )

    def list_planning_context(self, **values: Any) -> tuple[tuple[()], tuple[()]]:
        self.commands.append(values)
        return (), ()


class IntakeDurableStore:
    def __init__(self, request_id: UUID) -> None:
        self.calls: list[str] = []
        self.job = JobView(
            job_id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
            job_kind="interpretation.run",
            aggregate_id=request_id,
            state="review_required",
            attempt_count=1,
            max_attempts=6,
            available_at=datetime(2026, 9, 28, tzinfo=UTC),
            leased_until=None,
            cancellation_requested=False,
            last_error_code="model_invalid_output",
            created_at=datetime(2026, 9, 28, tzinfo=UTC),
            completed_at=None,
        )

    def ensure_job(self, **values: Any) -> JobView:
        self.calls.append("ensure_job")
        return self.job.model_copy(update={"state": "queued"})

    def get_job(self, **values: Any) -> JobView:
        self.calls.append("get_job")
        return self.job

    def retry_job(self, **values: Any) -> JobView:
        self.calls.append("retry_job")
        return self.job.model_copy(update={"state": "queued"})


def demo_intake_client(
    store: DemoIntakeStore, durable: IntakeDurableStore, *, demo: bool = True
) -> TestClient:
    context = CompanyContext(
        actor=FakeVerifier().verify("valid-token"),
        company_id=COMPANY_ID,
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=uuid4() if demo else None,
        demo_actor_session_id=uuid4() if demo else None,
        demo_planning_authority=demo,
    )
    application = create_app()
    application.dependency_overrides[require_company_context] = lambda: context
    application.dependency_overrides[get_interpretation_store] = lambda: store
    application.dependency_overrides[get_demo_intake_store] = lambda: store if demo else None
    application.dependency_overrides[get_durable_store] = lambda: durable
    return TestClient(application)


def test_demo_context_exposes_exact_supported_intake_without_starting_work() -> None:
    store = DemoIntakeStore(NORTHSTAR_INTAKE)
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.get(f"/v1/companies/{COMPANY_ID}/planning-context")
    assert response.status_code == 200
    assert response.json()["demo_intake"]["original_request"] == NORTHSTAR_INTAKE
    assert response.json()["demo_intake"]["kind"] == "northstar_launch"
    assert durable.calls == []


def test_non_demo_context_does_not_limit_freeform_intake() -> None:
    store = DemoIntakeStore("An ordinary organisational change.")
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable, demo=False) as client:
        response = client.get(f"/v1/companies/{COMPANY_ID}/planning-context")
    assert response.status_code == 200
    assert response.json()["demo_intake"] is None


def test_unsupported_demo_request_is_rejected_before_creation_or_provider_spend() -> None:
    store = DemoIntakeStore("A different free-form request.")
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests",
            headers=request_headers(),
            json=request_body(),
        )
    assert response.status_code == 422
    assert "approved Northstar launch" in response.json()["detail"]
    assert store.commands == []
    assert durable.calls == []


def test_canonical_demo_request_passes_intake_guard_without_rewriting_it() -> None:
    store = DemoIntakeStore(NORTHSTAR_INTAKE)
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests",
            headers=request_headers(),
            json={**request_body(), "original_request": NORTHSTAR_INTAKE},
        )
    assert response.status_code == 201
    assert store.commands[0]["command"].original_request == NORTHSTAR_INTAKE


def test_unsupported_saved_demo_request_cannot_enqueue_or_retry_interpretation() -> None:
    store = DemoIntakeStore("Legacy noncanonical request remains unchanged.")
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        enqueue = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}/interpret",
            headers=request_headers(),
        )
        retry = client.post(
            f"/v1/companies/{COMPANY_ID}/jobs/{durable.job.job_id}/retry",
            headers=request_headers(),
            json={"reason": "Attempt to bypass supported intake."},
        )
    assert enqueue.status_code == 422
    assert retry.status_code == 422
    assert durable.calls == ["get_job"]
    assert all("command" not in command for command in store.commands)
    assert store.prompt == "Legacy noncanonical request remains unchanged."


def test_supported_saved_demo_request_can_enqueue() -> None:
    store = DemoIntakeStore(NORTHSTAR_INTAKE)
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}/interpret",
            headers=request_headers(),
        )
    assert response.status_code == 202
    assert durable.calls == ["ensure_job"]


def test_legacy_demo_detail_is_readable_but_has_no_retry_permission() -> None:
    store = DemoIntakeStore("Legacy request with no typed scenario authority.")
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.get(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}",
            headers=request_headers(),
        )
    assert response.status_code == 200
    assert response.json()["original_request"] == store.prompt
    assert response.json()["intake_supported"] is False
    assert response.json()["intake_limitation"]
    assert response.json()["interpretation_job"]["can_retry"] is False
    assert durable.calls == []


def test_unsupported_demo_clarifications_do_not_create_a_derived_request() -> None:
    store = DemoIntakeStore("Legacy request with no typed scenario authority.")
    durable = IntakeDurableStore(store.request_id)
    with demo_intake_client(store, durable) as client:
        response = client.post(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}/clarifications",
            headers=request_headers(),
            json={
                "request_version": 1,
                "candidate_contract_id": str(uuid4()),
                "answers": {"task-owner": "Maya"},
            },
        )
    assert response.status_code == 422
    assert all("command" not in command for command in store.commands)


@pytest.mark.parametrize("job_kind,can_retry", [("plan.propose", False), ("planning.run", True)])
def test_fixed_authoring_progress_does_not_offer_unsupported_manual_recovery(
    job_kind: str,
    can_retry: bool,
) -> None:
    class StageStore(FakeStore):
        def get_request(self, **values: Any) -> PlanningRequestView:
            view = super().get_request(**values)
            return replace(
                view,
                status="interpreted",
                clarifications=(),
                planning_job_state="review_required",
                planning_job=PlanningStageJob(
                    job_id=uuid4(),
                    state="review_required",
                    attempt_count=1,
                    max_attempts=3,
                    last_error_code="fixed_authoring_budget_exhausted",
                    job_kind=job_kind,
                ),
            )

    store = StageStore()
    with client_for("manager", store) as client:
        response = client.get(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}",
            headers=request_headers(),
        )
    assert response.status_code == 200
    assert response.json()["planning_job_state"] == "review_required"
    assert response.json()["planning_job"]["can_retry"] is can_retry


def test_exhausted_interpretation_does_not_advertise_a_nonfunctional_retry() -> None:
    class ExhaustedStore(FakeStore):
        def get_request(self, **values: Any) -> PlanningRequestView:
            return replace(
                super().get_request(**values),
                status="failed",
                clarifications=(),
                interpretation_job_state="review_required",
                interpretation_job=PlanningStageJob(
                    job_id=uuid4(),
                    state="review_required",
                    attempt_count=3,
                    max_attempts=6,
                    last_error_code="interpretation_contract_rejected",
                    job_kind="interpretation.run",
                ),
            )

    store = ExhaustedStore()
    with client_for("manager", store) as client:
        response = client.get(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}",
            headers=request_headers(),
        )
    assert response.status_code == 200
    assert response.json()["interpretation_job"]["can_retry"] is False


@pytest.mark.parametrize(
    "job_kind,count,code,expected_count,expected_code,expected_retry",
    [
        ("plan.propose", 3, "model_output_truncated", 3, "model_output_truncated", True),
        ("plan.propose", 3, "private provider error text", 3, None, True),
        ("plan.propose", 5, None, 5, None, False),
        ("plan.propose", None, None, None, None, True),
        ("planning.run", 3, "model_output_truncated", None, None, True),
    ],
)
def test_public_progress_separates_worker_attempts_from_safe_ai_attempt_metadata(
    job_kind: str,
    count: int | None,
    code: str | None,
    expected_count: int | None,
    expected_code: str | None,
    expected_retry: bool,
) -> None:
    class AttemptStore(FakeStore):
        def get_request(self, **values: Any) -> PlanningRequestView:
            return replace(
                super().get_request(**values),
                status="interpreted",
                clarifications=(),
                planning_job_state="review_required",
                planning_job=PlanningStageJob(
                    job_id=uuid4(),
                    state="review_required",
                    attempt_count=1,
                    max_attempts=3,
                    last_error_code="fixed_plan_not_verified",
                    job_kind=job_kind,
                    model_call_count=count,
                    latest_model_error_code=code,
                ),
            )

    store = AttemptStore()
    with client_for("manager", store) as client:
        response = client.get(
            f"/v1/companies/{COMPANY_ID}/planning-requests/{store.request_id}",
            headers=request_headers(),
        )
    assert response.status_code == 200
    stage = response.json()["planning_job"]
    assert stage["attempt_count"] == 1
    assert stage["model_call_count"] == expected_count
    assert stage["latest_model_error_code"] == expected_code
    assert stage["can_retry"] is expected_retry
    assert "private provider error text" not in response.text
    assert set(stage) == {
        "job_id",
        "state",
        "attempt_count",
        "max_attempts",
        "last_error_code",
        "model_call_count",
        "latest_model_error_code",
        "can_retry",
    }
