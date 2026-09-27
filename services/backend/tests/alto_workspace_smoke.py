"""Explicit opt-in HTTP/DB smoke; only the separate disposable localhost database.

Run after migrations and alto_scenario.py, with ALTO_DISPOSABLE_DB_URL set. This does
not verify Supabase JWT issuance: its test Auth user and verifier are fixtures. All
workspace queries/commands use an actual NOINHERIT, non-owner API login and real RLS.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient

from coordination.api.main import create_app
from coordination.auth.dependencies import get_token_verifier
from coordination.auth.models import AuthenticatedUser
from coordination.config import Settings, get_settings
from coordination.durable.contracts import WorkerIdentity
from coordination.durable.persistence import PostgresDurableStore
from coordination.workspace.jobs import WorkspaceJobHandler

COMPANY = "11111111-1111-4111-8111-111111111111"


def smoke_settings(dsn: str) -> Settings:
    values: dict[str, Any] = {"_env_file": None, "environment": "test", "database_url": dsn}
    return Settings(**values)


def main() -> None:
    dsn = os.environ["ALTO_DISPOSABLE_DB_URL"]
    target = urlparse(dsn)
    if target.hostname != "127.0.0.1" or target.port != 55439:
        raise SystemExit("refusing database other than explicit disposable localhost:55439")
    user_id = uuid4()
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("""do $$ begin
          if not exists(select 1 from pg_roles where rolname='alto_workspace_audit') then
            create role alto_workspace_audit login noinherit password 'local-workspace-audit';
          end if; end $$""")
        connection.execute(
            "grant coordination_api to alto_workspace_audit with set true, inherit false"
        )
        connection.execute("""do $$ begin
          if not exists(select 1 from pg_roles where rolname='alto_workspace_worker_audit') then
            create role alto_workspace_worker_audit login noinherit
              password 'local-workspace-worker-audit';
          end if; end $$""")
        connection.execute(
            "grant coordination_worker to alto_workspace_worker_audit with set true, inherit false"
        )
        connection.execute(
            """insert into auth.users(id,aud,role,email,created_at,updated_at)
          values(%s,'authenticated','authenticated',%s,now(),now())""",
            (user_id, f"{user_id}@workspace-audit.invalid"),
        )
    api_dsn = "postgresql://alto_workspace_audit:local-workspace-audit@127.0.0.1:55439/postgres"
    with psycopg.connect(api_dsn) as connection:
        try:
            connection.execute("set role coordination_worker")
        except psycopg.errors.InsufficientPrivilege:
            connection.rollback()
        else:
            raise AssertionError("API login can assume worker role")

    class Verifier:
        def verify(self, token: str) -> AuthenticatedUser:
            assert token == "disposable-fixture-token"
            return AuthenticatedUser(user_id, "authenticated", uuid4(), "aal1")

    application = create_app()
    application.dependency_overrides[get_token_verifier] = Verifier
    application.dependency_overrides[get_settings] = lambda: smoke_settings(api_dsn)
    headers = {"Authorization": "Bearer disposable-fixture-token", "X-Company-ID": COMPANY}
    base = f"/v1/companies/{COMPANY}"
    count = 0
    with TestClient(application) as client:

        def call(method: str, path: str, body: Any = None, expected: int = 200) -> Any:
            nonlocal count
            response = client.request(
                method,
                path,
                headers={
                    **headers,
                    "Idempotency-Key": str(uuid4()),
                },
                **({"json": body} if body is not None else {}),
            )
            assert response.status_code == expected, (
                method,
                path,
                response.status_code,
                response.text,
            )
            count += 1
            return response.json()

        call(
            "POST",
            "/v1/demo/onboarding",
            {"display_name": "Disposable Workspace Auditor", "requested_role": "employee"},
        )
        call("GET", "/v1/session")
        run_id = call("POST", base + "/demo/runs", {"mode": "authored_replay"})["id"]
        headers["X-Demo-Run-ID"] = run_id
        listing = call("GET", base + "/demo/runs")
        actors = {actor["display_name"].split()[0]: actor["id"] for actor in listing["actors"]}

        def actor(name: str) -> None:
            headers.pop("X-Demo-Actor-Session-ID", None)
            selected = call(
                "POST", base + f"/demo/runs/{run_id}/actor-sessions", {"employee_id": actors[name]}
            )
            headers["X-Demo-Actor-Session-ID"] = selected["actor_session_id"]

        actor("Maya")
        workspace = call("GET", base + "/workspace")
        assert workspace["viewer"]["role"] == "manager"
        assert workspace["viewer"]["user_id"] == str(user_id)
        call("GET", base + "/home")
        call("GET", base + "/manager/actions")
        projects = call("GET", base + "/projects")["projects"]
        assert len(projects) == 1 and projects[0]["task_count"] == 0
        call("GET", base + f"/projects/{projects[0]['id']}/graph")
        people = call("GET", base + "/people")["people"]
        assert len(people) == 50
        call("GET", base + f"/people/{actors['Iris']}")
        call("GET", base + "/calendar?start=2026-09-28T00:00:00Z&end=2026-10-03T00:00:00Z")
        call("GET", base + "/connections")
        call("GET", base + "/me/preferences")
        actor("Iris")
        assert call("GET", base + "/workspace")["viewer"]["role"] == "employee"
        call(
            "POST",
            base + "/me/feedback",
            {"text": "Private test circumstances", "suggest_preference": False},
        )
        preference = call(
            "POST",
            base + "/me/employee-preferences",
            {"text": "I prefer one uninterrupted design block."},
        )
        preferences = call("GET", base + "/me/employee-preferences")
        current = next(
            item for item in preferences["preferences"] if item["id"] == preference["id"]
        )
        call(
            "POST",
            base + f"/me/employee-preferences/{preference['id']}/share",
            {
                "expected_row_version": current["row_version"],
                "manager_id": actors["Maya"],
            },
        )
        actor("Maya")
        shared = call("GET", base + f"/employee-preferences/{preference['id']}")
        assert "Private test circumstances" not in str(shared)
        call("GET", base + f"/people/{actors['Iris']}")
        actor("Jordan")
        call("GET", base + f"/employee-preferences/{preference['id']}", expected=404)
        actor("Iris")
        preferences = call("GET", base + "/me/employee-preferences")
        current = next(
            item for item in preferences["preferences"] if item["id"] == preference["id"]
        )
        call(
            "POST",
            base + f"/me/employee-preferences/{preference['id']}/revoke",
            {
                "expected_row_version": current["row_version"],
            },
        )
        actor("Maya")
        call("GET", base + f"/employee-preferences/{preference['id']}", expected=404)
        thread = call("POST", base + "/assistant/threads", {"context": {"kind": "global"}})
        call("GET", base + f"/assistant/threads/{thread['id']}")
        call(
            "POST",
            base + f"/assistant/threads/{thread['id']}/messages",
            {
                "context": {"kind": "global"},
                "content": "What is this project?",
            },
        )
        worker_dsn = (
            "postgresql://alto_workspace_worker_audit:local-workspace-worker-audit"
            "@127.0.0.1:55439/postgres"
        )
        worker_settings = smoke_settings(worker_dsn)
        worker = WorkerIdentity(uuid4(), "alto-workspace-smoke", "local", "test")
        durable = PostgresDurableStore(worker_dsn)
        durable.heartbeat(worker=worker, current_job_id=None)
        for _ in range(100):
            leased = durable.lease_jobs(worker=worker, limit=1, lease_seconds=120)
            if not leased:
                break
            job = leased[0]
            assert job.job_kind in {"assistant.respond", "outbox.deliver"}, job.job_kind
            try:
                result = (
                    WorkspaceJobHandler(worker_settings, "assistant.respond")(job)
                    if job.job_kind == "assistant.respond"
                    else durable.deliver_outbox(lease=job)
                )
                durable.complete_job(
                    lease=job, worker_id=worker.worker_id, result=result, metrics={}
                )
            except Exception:
                durable.fail_job(
                    lease=job,
                    worker_id=worker.worker_id,
                    error_code="smoke_failure",
                    error_message="Disposable smoke failed",
                    retryable=False,
                    ambiguous=False,
                    metrics={},
                )
                raise
            if job.payload.get("thread_id") == thread["id"]:
                break
        answered = call("GET", base + f"/assistant/threads/{thread['id']}")
        assert answered["status"] == "completed", answered
        assert any(message["role"] == "assistant" for message in answered["messages"])
        actor("Iris")
        call("GET", base + f"/assistant/threads/{thread['id']}", expected=404)
        profile = call("GET", base + f"/people/{actors['Iris']}")
        call(
            "PATCH",
            base + "/me/profile",
            {
                "expected_row_version": profile["row_version"],
                "skills": ["Design", "Writing"],
            },
        )
        current_session = headers["X-Demo-Actor-Session-ID"]
        call(
            "POST",
            base + f"/demo/runs/{uuid4()}/actor-sessions/{current_session}/end",
            expected=404,
        )
        call("POST", base + f"/demo/runs/{run_id}/actor-sessions/{current_session}/end")
        call("GET", base + "/workspace", expected=404)
        assert UUID(run_id)
    print(f"ALTO workspace smoke passed: {count} HTTP/DB assertions; no hosted writes.")


if __name__ == "__main__":
    main()
