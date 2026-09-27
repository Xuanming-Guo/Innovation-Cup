"""Explicit disposable-loopback integration exercise; never contacts a hosted database.

Set ALTO_DISPOSABLE_DB_URL and run this module directly after migrations and scenario
provisioning. It creates a distinct synthetic Auth visitor/run and uses production
request, durable lease/handlers, exact approval/disclosure and commit paths.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier, Literal
from pydantic import SecretStr

from coordination.approval.contracts import ApprovalCommand, CommitCommand
from coordination.approval.persistence import PostgresApprovalStore
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.db.session import authenticated_transaction, company_transaction
from coordination.durable.contracts import WorkerIdentity
from coordination.durable.handlers import build_handlers
from coordination.durable.persistence import PostgresDurableStore
from coordination.employee.contracts import ReviewCommand, SubmissionCommand, TaskTransitionCommand
from coordination.employee.persistence import PostgresEmployeeStore
from coordination.planning.northstar import REVIEWS, person_id
from coordination.workspace.northstar import create_northstar_request
from coordination.workspace.persistence import PostgresWorkspaceStore

COMPANY = UUID("11111111-1111-4111-8111-111111111111")


def runtime_connections(operator_dsn: str) -> tuple[str, str]:
    """Provision only disposable fixture logins; business operations cannot switch roles."""
    connections = []
    for suffix, allowed, denied in (
        ("api", "coordination_api", "coordination_worker"),
        ("worker", "coordination_worker", "coordination_api"),
    ):
        login = f"alto_planning_{suffix}_audit"
        password = f"local-planning-{suffix}-audit"
        with psycopg.connect(operator_dsn, autocommit=True) as connection:
            exists = connection.execute(
                "select 1 from pg_roles where rolname=%s", (login,)
            ).fetchone()
            if not exists:
                connection.execute(
                    SQL("create role {} login noinherit password {}").format(
                        Identifier(login), Literal(password)
                    )
                )
            connection.execute(
                SQL("grant {} to {} with set true, inherit false").format(
                    Identifier(allowed), Identifier(login)
                )
            )
        runtime_dsn = make_conninfo(operator_dsn, user=login, password=password)
        with psycopg.connect(runtime_dsn) as connection:
            flags = connection.execute(
                "select rolsuper,rolbypassrls,rolinherit from pg_roles where rolname=current_user"
            ).fetchone()
            assert flags == (False, False, False)
            try:
                connection.execute(SQL("set role {}").format(Identifier(denied)))
            except psycopg.errors.InsufficientPrivilege:
                connection.rollback()
            else:
                raise AssertionError(f"{suffix} fixture login can assume forbidden {denied}")
        connections.append(runtime_dsn)
    return connections[0], connections[1]


def complete_execution(operator_dsn: str, api_dsn: str, run_id: UUID) -> dict[str, object]:
    """Resume only this script's own disposable visitor; never manufacture accepted rows."""
    with psycopg.connect(operator_dsn, row_factory=dict_row, connect_timeout=5) as connection:
        owner = connection.execute(
            """select m.id as membership_id,m.user_id,u.email
            from app.demo_runs r join app.company_memberships m
              on m.company_id=r.company_id and m.id=r.owner_membership_id
            join auth.users u on u.id=m.user_id where r.company_id=%s and r.id=%s""",
            (COMPANY, run_id),
        ).fetchone()
    if (
        owner is None
        or not owner["email"].startswith("alto-planning-")
        or not owner["email"].endswith("@example.invalid")
    ):
        raise RuntimeError("Refusing to execute a run not created by this disposable smoke script")
    base = CompanyContext(
        actor=AuthenticatedUser(
            user_id=owner["user_id"],
            role="authenticated",
            session_id=uuid4(),
            assurance_level="aal1",
        ),
        company_id=COMPANY,
        membership_id=owner["membership_id"],
        administrative_role="member",
        employee_id=None,
        demo_run_id=run_id,
    )
    employees = PostgresEmployeeStore(api_dsn)
    workspace = PostgresWorkspaceStore(api_dsn)

    def select_actor(person: str) -> CompanyContext:
        with company_transaction(
            api_dsn,
            role="coordination_api",
            actor_id=base.actor.user_id,
            company_id=COMPANY,
            demo_run_id=run_id,
            purpose="test:select-executor",
        ) as connection:
            selected = connection.execute(
                "select app.select_demo_actor(%s,%s,%s) as id",
                (COMPANY, run_id, person_id(COMPANY, person)),
            ).fetchone()
        assert selected is not None
        return replace(
            base,
            demo_actor_session_id=selected["id"],
            simulated_employee_id=person_id(COMPANY, person),
        )

    def transaction(context: CompanyContext, purpose: str):  # type: ignore[no-untyped-def]
        return company_transaction(
            api_dsn,
            role="coordination_api",
            actor_id=base.actor.user_id,
            company_id=COMPANY,
            demo_run_id=run_id,
            demo_actor_session_id=context.demo_actor_session_id,
            purpose=purpose,
        )

    manager = select_actor("maya")
    with transaction(manager, "test:execution-ledger") as connection:
        tasks = connection.execute(
            """select w.task_id,w.task_code,w.start_at,w.finish_at,w.project_id,
            e.synthetic_key as owner from app.work_items w join app.execution_resources r
              on r.company_id=w.company_id and r.id=w.owner_resource_id
            join app.employee_profiles e on e.company_id=r.company_id and e.id=r.employee_id
            where w.company_id=%s order by w.start_at,w.task_code""",
            (COMPANY,),
        ).fetchall()
    assert len(tasks) == 17
    by_key = {row["task_code"].lower(): row for row in tasks}
    subjects = {review: subject for subject, review in REVIEWS.items()}
    events = sorted(
        [(row["start_at"], 1, key, "start") for key, row in by_key.items()]
        + [(row["finish_at"], 0, key, "finish") for key, row in by_key.items()]
    )
    for instant, _phase, key, action in events:
        manager = select_actor("maya")
        with transaction(manager, "test:scenario-clock") as connection:
            clock = connection.execute(
                "select clock_at,clock_version from app.demo_runs where company_id=%s and id=%s",
                (COMPANY, run_id),
            ).fetchone()
            assert clock is not None
            if instant > clock["clock_at"]:
                before = connection.execute(
                    "select task_id,status from app.work_items "
                    "where company_id=%s order by task_id",
                    (COMPANY,),
                ).fetchall()
                connection.execute(
                    "select app.advance_demo_clock(%s,%s,%s,%s,%s)",
                    (
                        COMPANY,
                        run_id,
                        clock["clock_version"],
                        instant,
                        f"execution-clock-{run_id}-{clock['clock_version']}",
                    ),
                )
                after = connection.execute(
                    "select task_id,status from app.work_items "
                    "where company_id=%s order by task_id",
                    (COMPANY,),
                ).fetchall()
                assert before == after, "Advancing the clock must not execute or accept work"
        context = select_actor(by_key[key]["owner"])
        task_uuid = by_key[key]["task_id"]
        with transaction(context, "test:current-task") as connection:
            current = connection.execute(
                "select status,row_version from app.work_items where company_id=%s and task_id=%s",
                (COMPANY, task_uuid),
            ).fetchone()
        assert current is not None
        if current["status"] == "accepted":
            continue
        print(f"Execution {key.upper()} {action}", flush=True)
        if action == "start":
            if current["status"] == "assigned":
                acknowledged = employees.transition(
                    context=context,
                    task_id=task_uuid,
                    command=TaskTransitionCommand(
                        command="acknowledge",
                        expected_task_version=current["row_version"],
                        idempotency_key=f"execution-ack-{task_uuid}",
                        correlation_id=uuid4(),
                    ),
                )
                current = {
                    "status": acknowledged.task_status,
                    "row_version": acknowledged.task_version,
                }
            if current["status"] == "acknowledged":
                employees.transition(
                    context=context,
                    task_id=task_uuid,
                    command=TaskTransitionCommand(
                        command="start",
                        expected_task_version=current["row_version"],
                        idempotency_key=f"execution-start-{task_uuid}",
                        correlation_id=uuid4(),
                    ),
                )
            continue
        if key in {"r1", "r2"}:
            required = None
            if key == "r2":
                with transaction(context, "test:exact-final-artifact") as connection:
                    required = connection.execute(
                        """select id,submission_digest from app.submissions
                        where company_id=%s and task_id=%s and state='submitted'
                        order by version desc limit 1""",
                        (COMPANY, by_key["s4"]["task_id"]),
                    ).fetchone()
                assert required is not None
            with transaction(context, "test:explicit-gate-approval") as connection:
                result = connection.execute(
                    "select app.approve_alto_gate(%s,%s,%s,%s,%s,%s,%s) as value",
                    (
                        COMPANY,
                        task_uuid,
                        current["row_version"],
                        required["id"] if required else None,
                        required["submission_digest"] if required else None,
                        f"execution-gate-{task_uuid}",
                        uuid4(),
                    ),
                ).fetchone()
                assert result is not None and result["value"]["status"] == "accepted"
            continue
        if key in subjects:
            subject_id = by_key[subjects[key]]["task_id"]
        else:
            subject_id = task_uuid
            if current["status"] != "submitted":
                employees.submit(
                    context=context,
                    task_id=task_uuid,
                    command=SubmissionCommand(
                        narrative=(
                            f"Disposable authored execution: exact {key.upper()} "
                            "deliverable and acceptance evidence."
                        ),
                        external_evidence_refs=(
                            f"https://evidence.example.invalid/{run_id}/{key}/v1",
                        ),
                        reported_active_minutes=int(
                            (by_key[key]["finish_at"] - by_key[key]["start_at"]).total_seconds()
                            / 60
                        ),
                        expected_task_version=current["row_version"],
                        idempotency_key=f"execution-submit-{task_uuid}",
                        correlation_id=uuid4(),
                    ),
                )
            if key not in {"m1", "s1"}:
                continue
        with transaction(context, "test:exact-review-artifact") as connection:
            submission = connection.execute(
                """select id from app.submissions where company_id=%s
                and task_id=%s and state='submitted' order by version desc limit 1""",
                (COMPANY, subject_id),
            ).fetchone()
        assert submission is not None
        actual = employees.get_submission(context=context, submission_id=submission["id"])
        employees.review(
            context=context,
            submission_id=actual.submission_id,
            command=ReviewCommand(
                expected_submission_version=actual.version,
                submission_digest=actual.submission_digest,
                decision="accepted",
                criterion_findings=({"criterion": "Exact submitted artifact", "passed": True},),
                idempotency_key=f"execution-review-{actual.submission_id}",
                correlation_id=uuid4(),
            ),
        )
    manager = select_actor("maya")
    with transaction(manager, "test:completed-evidence") as connection:
        summary = connection.execute(
            """select count(*) as total,count(*) filter(where status='accepted') as accepted
            from app.work_items where company_id=%s""",
            (COMPANY,),
        ).fetchone()
        project = connection.execute(
            "select status,accepted_at,accepted_by_employee_id from app.projects "
            "where company_id=%s and id=%s",
            (COMPANY, tasks[0]["project_id"]),
        ).fetchone()
        blocks = connection.execute(
            "select count(*) as count from app.committed_schedule_blocks "
            "where company_id=%s and active",
            (COMPANY,),
        ).fetchone()
        evidence = connection.execute(
            "select count(*) as count from app.task_gate_uses where company_id=%s", (COMPANY,)
        ).fetchone()
        d0 = connection.execute(
            "select id from app.ai_plan_proposals where company_id=%s "
            "and version=1 order by created_at limit 1",
            (COMPANY,),
        ).fetchone()
        readiness_event = connection.execute(
            """select from_status,to_status from app.task_events
            where company_id=%s and task_id=%s and event_type='accepted'""",
            (COMPANY, by_key["r1"]["task_id"]),
        ).fetchone()
    assert summary and summary["total"] == summary["accepted"] == 17
    assert project and project["status"] == "completed" and project["accepted_at"]
    assert project["accepted_by_employee_id"] == person_id(COMPANY, "maya")
    assert blocks and blocks["count"] == 18, "Review decisions must not reserve capacity twice"
    assert evidence and evidence["count"] > 0
    assert readiness_event == {"from_status": "in_progress", "to_status": "accepted"}
    current_graph = workspace.graph(manager, tasks[0]["project_id"])
    assert current_graph.project.status == "completed" and not current_graph.is_candidate_preview
    assert d0 is not None
    failed_graph = workspace.graph(manager, tasks[0]["project_id"], proposal_id=d0["id"])
    assert failed_graph.check_status == "VIOLATIONS_FOUND" and not failed_graph.can_approve
    return {
        "run_id": str(run_id),
        "accepted_tasks": 17,
        "project_status": "completed",
        "committed_capacity_blocks": 18,
        "exact_gate_evidence_uses": evidence["count"],
        "d0_history": "real violation read-only",
        "clock_advances_do_not_execute": True,
    }


def main() -> None:
    dsn = os.environ["ALTO_DISPOSABLE_DB_URL"]
    target = conninfo_to_dict(dsn)
    if target.get("host") not in {"127.0.0.1", "localhost"} or target.get("port") != "55439":
        raise RuntimeError("Only the explicitly designated loopback disposable database is allowed")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-run", type=UUID)
    args = parser.parse_args()
    api_dsn, worker_dsn = runtime_connections(dsn)
    if args.resume_run:
        resumed = complete_execution(dsn, api_dsn, args.resume_run)
        print(json.dumps(resumed, default=str), flush=True)
        return
    user_id = uuid4()
    print("Connecting to designated disposable DB", flush=True)
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5) as connection:
        pending = connection.execute(
            "select count(*) as count from app.durable_jobs "
            "where state in ('queued','leased','retry_scheduled')"
        ).fetchone()
        if pending and pending["count"]:
            raise RuntimeError("Another visitor has queued jobs; obtain an exclusive worker window")
        connection.execute(
            "insert into auth.users(id,email) values(%s,%s)",
            (user_id, f"alto-planning-{user_id}@example.invalid"),
        )
    print("Bootstrapping independent synthetic visitor", flush=True)
    with authenticated_transaction(
        api_dsn, actor_id=user_id, purpose="test:bootstrap"
    ) as connection:
        member = connection.execute(
            "select app.bootstrap_demo_membership(%s,'member',%s) as value",
            ("ALTO planning smoke", f"planning-smoke-bootstrap-{user_id}"),
        ).fetchone()["value"]
    context = CompanyContext(
        actor=AuthenticatedUser(
            user_id=user_id, role="authenticated", session_id=uuid4(), assurance_level="aal1"
        ),
        company_id=COMPANY,
        membership_id=UUID(member["membership_id"]),
        administrative_role="member",
        employee_id=None,
    )
    with company_transaction(
        api_dsn, role="coordination_api", actor_id=user_id, company_id=COMPANY, purpose="test:fork"
    ) as connection:
        print("Initialising independent authored D0 run", flush=True)
        run_id = connection.execute(
            "select app.fork_demo_run(%s,'authored_d0_check',null,%s) as id",
            (COMPANY, f"planning-smoke-run-{user_id}"),
        ).fetchone()["id"]
        connection.execute("select app.initialise_demo_run(%s,%s)", (COMPANY, run_id))
        actor_session = connection.execute(
            "select app.select_demo_actor(%s,%s,%s) as id",
            (COMPANY, run_id, person_id(COMPANY, "maya")),
        ).fetchone()["id"]
    context = replace(
        context,
        demo_run_id=run_id,
        demo_actor_session_id=actor_session,
        simulated_employee_id=person_id(COMPANY, "maya"),
    )
    workspace = PostgresWorkspaceStore(api_dsn)
    request = create_northstar_request(
        store=workspace,
        context=context,
        run_id=run_id,
        idempotency_key=f"planning-smoke-request-{user_id}",
    )
    print("Launch request accepted; processing normal durable queue", flush=True)
    setting_values: dict[str, Any] = {
        "_env_file": None,
        "database_url": SecretStr(worker_dsn),
        "environment": "test",
    }
    settings = Settings(**setting_values)
    durable = PostgresDurableStore(worker_dsn)
    worker = WorkerIdentity(
        worker_id=uuid4(),
        instance_name="alto-planning-smoke",
        build_commit="disposable-verification",
        environment="test",
    )
    durable.heartbeat(worker=worker, current_job_id=None)
    handlers = build_handlers(settings, durable)
    stages: list[str] = []
    plan_id = None
    for _ in range(8):
        jobs = durable.lease_jobs(worker=worker, limit=1, lease_seconds=240)
        if not jobs:
            break
        lease = jobs[0]
        print("Running " + lease.job_kind, flush=True)
        if lease.demo_run_id != run_id:
            raise RuntimeError("Unexpected outside-run job; exclusive worker window was violated")
        try:
            result = handlers[lease.job_kind](lease)
        except Exception:
            durable.fail_job(
                lease=lease,
                worker_id=worker.worker_id,
                error_code="smoke_failure",
                error_message="Disposable integration failed; inspect the operator traceback.",
                retryable=False,
                ambiguous=False,
                metrics={},
            )
            raise
        durable.complete_job(lease=lease, worker_id=worker.worker_id, result=result, metrics={})
        stages.append(lease.job_kind)
        if lease.job_kind == "plan.propose":
            plan_id = UUID(str(result.values["plan_id"]))
            break
    assert stages == ["interpretation.run", "planning.materialize", "plan.propose"], stages
    assert plan_id is not None
    approval = PostgresApprovalStore(api_dsn)
    review = approval.get_review(context=context, plan_id=plan_id)
    assert len(review.tasks) == 17 and len(review.requirements) == 18
    for requirement in review.requirements:
        approval.decide(
            context=context,
            plan_id=plan_id,
            command=ApprovalCommand(
                requirement_id=requirement.requirement_id,
                decision="approved",
                explanation="Disposable exact-version verification",
                artifact_digest=requirement.artifact_digest,
                binding=review.binding,
                idempotency_key=f"planning-smoke-approve-{requirement.requirement_id}",
                correlation_id=uuid4(),
            ),
        )
    committed = approval.commit(
        context=context,
        plan_id=plan_id,
        command=CommitCommand(
            binding=review.binding,
            idempotency_key=f"planning-smoke-commit-{plan_id}",
            correlation_id=uuid4(),
        ),
    )
    with company_transaction(
        api_dsn,
        role="coordination_api",
        actor_id=user_id,
        company_id=COMPANY,
        demo_run_id=run_id,
        demo_actor_session_id=actor_session,
        purpose="test:evidence",
    ) as connection:
        checks = connection.execute(
            """select proposal.version,verification.product_status
            from app.ai_plan_proposals proposal join app.plan_verification_runs verification
              on verification.company_id=proposal.company_id
              and verification.proposal_id=proposal.id
            where proposal.company_id=%s order by proposal.version""",
            (COMPANY,),
        ).fetchall()
        counts = connection.execute(
            """select count(*) as tasks,
            count(employee_brief_version_id) as task_briefs
            from app.work_items where company_id=%s""",
            (COMPANY,),
        ).fetchone()
        assert [(row["version"], row["product_status"]) for row in checks] == [
            (1, "VIOLATIONS_FOUND"),
            (2, "CHECKED"),
        ]
        assert counts and counts["tasks"] == counts["task_briefs"] == 17
    print(
        json.dumps(
            {
                "visitor_id": str(user_id),
                "run_id": str(run_id),
                "request_id": request["request_id"],
                "plan_id": str(plan_id),
                "stages": stages,
                "checks": [dict(row) for row in checks],
                "requirements_approved": 18,
                "committed_tasks": 17,
                "task_scoped_briefs": 17,
                "company_revision": committed.company_revision,
            },
            default=str,
        )
    )
    print(json.dumps(complete_execution(dsn, api_dsn, run_id), default=str), flush=True)


if __name__ == "__main__":
    main()
