"""Exercise the cross-layer API/worker database contract against local Supabase only."""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
from coordination.approval.contracts import ApprovalCommand, CommitCommand
from coordination.approval.persistence import PostgresApprovalStore
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.durable.contracts import WorkerIdentity
from coordination.durable.handlers import build_handlers
from coordination.durable.persistence import PostgresDurableStore
from coordination.durable.runner import DurableWorker
from coordination.employee.contracts import (
    ReviewCommand,
    SubmissionCommand,
    TaskTransitionCommand,
)
from coordination.employee.persistence import PostgresEmployeeStore
from coordination.interpretation.persistence import (
    CreatePlanningRequest,
    PostgresInterpretationStore,
)
from demo_tenant import (
    CAPACITY_SOURCE_ID,
    DEMO_COMPANY_ID,
    EMPLOYEE_EMPLOYEE_ID,
    EMPLOYEE_MEMBERSHIP_ID,
    HR_SOURCE_ID,
    MANAGER_EMPLOYEE_ID,
    MANAGER_MEMBERSHIP_ID,
    SOFTWARE_SOURCE_ID,
    seed,
)
from pydantic import SecretStr

LOCAL_ADMIN_DSN = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
API_LOGIN = "coordination_api_local_audit"
API_PASSWORD = "local-api-audit"
WORKER_LOGIN = "coordination_worker_local_audit"
WORKER_PASSWORD = "local-worker-audit"
MANAGER_USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
EMPLOYEE_USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")


def require_local_database(dsn: str) -> None:
    parsed = urlparse(dsn)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 54322:
        raise SystemExit("runtime-role verification refuses every non-local Supabase database")


def provision_local_fixture(admin_dsn: str) -> None:
    os.environ["COORDINATION_ENVIRONMENT"] = "test"
    os.environ["DEMO_MANAGER_USER_ID"] = str(MANAGER_USER_ID)
    os.environ["DEMO_EMPLOYEE_USER_ID"] = str(EMPLOYEE_USER_ID)
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(
            """
            insert into auth.users (
              id, instance_id, aud, role, email, encrypted_password, created_at, updated_at
            ) values
              (%s, '00000000-0000-0000-0000-000000000000',
               'authenticated', 'authenticated', 'local-manager@example.invalid',
               extensions.crypt('local-test-only', extensions.gen_salt('bf')),
               clock_timestamp(), clock_timestamp()),
              (%s, '00000000-0000-0000-0000-000000000000',
               'authenticated', 'authenticated', 'local-employee@example.invalid',
               extensions.crypt('local-test-only', extensions.gen_salt('bf')),
               clock_timestamp(), clock_timestamp())
            on conflict (id) do nothing
            """,
            (MANAGER_USER_ID, EMPLOYEE_USER_ID),
        )
        connection.execute(
            "select app_private.reset_demo_company(%s)",
            (DEMO_COMPANY_ID,),
        )
    with psycopg.connect(admin_dsn) as connection:
        seed(connection)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(
            f"""
            do $$
            begin
              if not exists (select 1 from pg_roles where rolname = '{API_LOGIN}') then
                create role {API_LOGIN} login password '{API_PASSWORD}' noinherit;
              end if;
              if not exists (select 1 from pg_roles where rolname = '{WORKER_LOGIN}') then
                create role {WORKER_LOGIN} login password '{WORKER_PASSWORD}' noinherit;
              end if;
            end
            $$
            """
        )
        connection.execute(f"alter role {API_LOGIN} password '{API_PASSWORD}'")
        connection.execute(f"alter role {WORKER_LOGIN} password '{WORKER_PASSWORD}'")
        connection.execute(
            f"grant coordination_api to {API_LOGIN} with set true, inherit false"
        )
        connection.execute(
            f"grant coordination_worker to {WORKER_LOGIN} with set true, inherit false"
        )


def assert_role_separation(api_dsn: str, worker_dsn: str) -> None:
    for dsn, forbidden_role in (
        (api_dsn, "coordination_worker"),
        (worker_dsn, "coordination_api"),
    ):
        try:
            with psycopg.connect(dsn) as connection:
                connection.execute(f"set role {forbidden_role}")
        except psycopg.errors.InsufficientPrivilege:
            continue
        raise RuntimeError(f"runtime login unexpectedly assumed {forbidden_role}")


def manager_context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(
            user_id=MANAGER_USER_ID,
            role="authenticated",
            session_id=uuid4(),
            assurance_level="aal2",
        ),
        company_id=DEMO_COMPANY_ID,
        membership_id=MANAGER_MEMBERSHIP_ID,
        administrative_role="company_admin",
        employee_id=MANAGER_EMPLOYEE_ID,
    )


def employee_context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(
            user_id=EMPLOYEE_USER_ID,
            role="authenticated",
            session_id=uuid4(),
            assurance_level="aal1",
        ),
        company_id=DEMO_COMPANY_ID,
        membership_id=EMPLOYEE_MEMBERSHIP_ID,
        administrative_role="member",
        employee_id=EMPLOYEE_EMPLOYEE_ID,
    )


def run_workflow(api_dsn: str, worker_dsn: str) -> dict[str, object]:
    context = manager_context()
    audit_id = uuid4().hex
    request_store = PostgresInterpretationStore(api_dsn)
    request = request_store.create_request(
        context=context,
        command=CreatePlanningRequest(
            project_id=None,
            original_request=(
                "Coordinate the approved software release and internal onboarding work."
            ),
            selected_source_ids=(
                SOFTWARE_SOURCE_ID,
                HR_SOURCE_ID,
                CAPACITY_SOURCE_ID,
            ),
            requested_priority_key=None,
            requested_deadline=None,
            requested_deadline_timezone=None,
            idempotency_key=f"local-audit-request-{audit_id}",
        ),
    )
    api_durable = PostgresDurableStore(api_dsn)
    ensured = api_durable.ensure_job(
        context=context,
        job_kind="interpretation.run",
        aggregate_id=request.request_id,
        idempotency_key=f"local-audit-ensure-{audit_id}",
        command_digest=hashlib.sha256(str(request.request_id).encode()).digest(),
        correlation_id=uuid4(),
    )

    settings = Settings(
        environment="test",
        database_url=SecretStr(worker_dsn),
        interpretation_mode="fixture",
        worker_lease_seconds=30,
        worker_renewal_seconds=10,
    )
    worker_store = PostgresDurableStore(worker_dsn)
    worker = DurableWorker(
        store=worker_store,
        worker=WorkerIdentity(
            worker_id=uuid4(),
            instance_name="local-runtime-role-audit",
            build_commit="local-audit",
            environment="test",
        ),
        handlers=build_handlers(settings, worker_store),
        batch_size=1,
        lease_seconds=30,
        renewal_seconds=10,
        emit=lambda _event: None,
    )

    cycles: list[dict[str, int]] = []
    view = request_store.get_request(context=context, request_id=request.request_id)
    for _ in range(8):
        if view.plan_id is not None:
            break
        cycle = worker.run_once()
        cycles.append(asdict(cycle))
        view = request_store.get_request(context=context, request_id=request.request_id)
    if view.plan_id is None:
        raise RuntimeError(
            "local runtime-role workflow did not create a plan; "
            f"request_status={view.status}, cycles={cycles}"
        )
    if any(
        cycle["retry_scheduled"]
        or cycle["dead_letter"]
        or cycle["review_required"]
        or cycle["lease_lost"]
        for cycle in cycles
    ):
        raise RuntimeError(f"local runtime-role workflow recorded a failure: {cycles}")

    plan_id = view.plan_id
    approval_store = PostgresApprovalStore(api_dsn)
    review = approval_store.get_review(context=context, plan_id=plan_id)
    for index, requirement in enumerate(review.requirements, start=1):
        approval_store.decide(
            context=context,
            plan_id=plan_id,
            command=ApprovalCommand(
                requirement_id=requirement.requirement_id,
                decision="approved",
                artifact_digest=requirement.artifact_digest,
                binding=review.binding,
                idempotency_key=f"local-audit-approval-{index:04d}-{audit_id}",
                correlation_id=uuid4(),
            ),
        )
    approved_review = approval_store.get_review(context=context, plan_id=plan_id)
    if not approved_review.can_commit:
        raise RuntimeError("the fully approved synthetic plan did not become committable")
    commitment = approval_store.commit(
        context=context,
        plan_id=plan_id,
        command=CommitCommand(
            binding=approved_review.binding,
            idempotency_key=f"local-audit-commit-{audit_id}",
            correlation_id=uuid4(),
        ),
    )
    committed_review = approval_store.get_review(context=context, plan_id=plan_id)
    if committed_review.status != "committed":
        raise RuntimeError("the approved synthetic plan did not remain committed")

    outbox_cycle = worker.run_once()
    if outbox_cycle.succeeded != 1:
        raise RuntimeError(f"committed-plan outbox delivery failed: {asdict(outbox_cycle)}")
    employee = employee_context()
    employee_store = PostgresEmployeeStore(api_dsn)
    tasks = (
        *employee_store.list_tasks(context=employee, view="today"),
        *employee_store.list_tasks(context=employee, view="upcoming"),
    )
    if not tasks or any(task.approved_brief is None for task in tasks):
        raise RuntimeError("committed employee work or its approved brief is unavailable")
    task = tasks[0]
    acknowledged = employee_store.transition(
        context=employee,
        task_id=task.task_id,
        command=TaskTransitionCommand(
            command="acknowledge",
            expected_task_version=task.row_version,
            idempotency_key=f"local-audit-acknowledge-{audit_id}",
            correlation_id=uuid4(),
        ),
    )
    started = employee_store.transition(
        context=employee,
        task_id=task.task_id,
        command=TaskTransitionCommand(
            command="start",
            expected_task_version=acknowledged.task_version,
            idempotency_key=f"local-audit-start-{audit_id}",
            correlation_id=uuid4(),
        ),
    )
    submission = employee_store.submit(
        context=employee,
        task_id=task.task_id,
        command=SubmissionCommand(
            narrative="Completed the synthetic audited deliverable and checked its handoff.",
            reported_active_minutes=30,
            expected_task_version=started.task_version,
            idempotency_key=f"local-audit-submit-{audit_id}",
            correlation_id=uuid4(),
        ),
    )
    pending = employee_store.list_pending_reviews(context=context)
    pending_submission = next(
        (item for item in pending if item.submission_id == submission.submission_id),
        None,
    )
    if pending_submission is None:
        raise RuntimeError("the employee submission was absent from the manager review queue")
    accepted = employee_store.review(
        context=context,
        submission_id=submission.submission_id,
        command=ReviewCommand(
            expected_submission_version=pending_submission.version,
            submission_digest=pending_submission.submission_digest,
            decision="accepted",
            idempotency_key=f"local-audit-review-{audit_id}",
            correlation_id=uuid4(),
        ),
    )
    if accepted.task_status != "accepted":
        raise RuntimeError("the reviewed synthetic task did not reach accepted state")
    manager_notifications = api_durable.list_notifications(
        context=context,
        after_created_at=None,
        after_id=None,
        limit=50,
    )
    employee_notifications = api_durable.list_notifications(
        context=employee,
        after_created_at=None,
        after_id=None,
        limit=50,
    )
    if not manager_notifications.notifications:
        raise RuntimeError("the committed-plan outbox produced no manager notification")
    if employee_notifications.notifications:
        raise RuntimeError("a private plan notification leaked into the employee inbox")
    return {
        "request_created": request.created,
        "ensure_state": ensured.state,
        "request_status": view.status,
        "interpretation_job_state": view.interpretation_job_state,
        "materialization_job_state": view.materialization_job_state,
        "planning_job_state": view.planning_job_state,
        "plan_created": True,
        "approval_requirements": len(review.requirements),
        "commit_status": commitment.status,
        "employee_tasks": len(tasks),
        "employee_submission_state": submission.state,
        "employee_review_decision": accepted.decision,
        "manager_notifications": len(manager_notifications.notifications),
        "employee_plan_notifications": len(employee_notifications.notifications),
        "worker_cycles": len(cycles),
    }


def main() -> int:
    admin_dsn = os.environ.get("SUPABASE_DB_URL", LOCAL_ADMIN_DSN)
    require_local_database(admin_dsn)
    parsed = urlparse(admin_dsn)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 54322
    database = parsed.path.lstrip("/") or "postgres"
    api_dsn = f"postgresql://{API_LOGIN}:{API_PASSWORD}@{host}:{port}/{database}"
    worker_dsn = (
        f"postgresql://{WORKER_LOGIN}:{WORKER_PASSWORD}@{host}:{port}/{database}"
    )
    provision_local_fixture(admin_dsn)
    assert_role_separation(api_dsn, worker_dsn)
    print(run_workflow(api_dsn, worker_dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
