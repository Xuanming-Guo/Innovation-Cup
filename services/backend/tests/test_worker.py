from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import SecretStr

from coordination.config import Settings
from coordination.durable.contracts import JobLease, JobResult, WorkerIdentity
from coordination.durable.persistence import DurableStoreError
from coordination.durable.runner import DurableWorker
from coordination.worker import main as worker_main

COMPANY_ID = UUID("11111111-1111-4111-8111-111111111111")
JOB_ID = UUID("22222222-2222-4222-8222-222222222222")
REQUEST_ID = UUID("33333333-3333-4333-8333-333333333333")
WORKER_ID = UUID("44444444-4444-4444-8444-444444444444")
LEASE_TOKEN = UUID("55555555-5555-4555-8555-555555555555")
MEMBERSHIP_ID = UUID("66666666-6666-4666-8666-666666666666")
USER_ID = UUID("77777777-7777-4777-8777-777777777777")
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def lease() -> JobLease:
    return JobLease(
        job_id=JOB_ID,
        company_id=COMPANY_ID,
        job_kind="interpretation.run",
        aggregate_id=REQUEST_ID,
        payload={"request_id": str(REQUEST_ID)},
        requested_by_membership_id=MEMBERSHIP_ID,
        requested_by_user_id=USER_ID,
        administrative_role="manager",
        employee_id=None,
        correlation_id=JOB_ID,
        attempt_count=1,
        max_attempts=6,
        lease_token=LEASE_TOKEN,
        leased_until=NOW + timedelta(minutes=2),
    )


class FakeDurableStore:
    def __init__(self, *, renew_result: bool = True) -> None:
        self.leases: tuple[JobLease, ...] = (lease(),)
        self.renew_result = renew_result
        self.renewed = threading.Event()
        self.completed: list[JobResult] = []
        self.failures: list[tuple[str, bool, bool]] = []
        self.heartbeats: list[UUID | None] = []

    def lease_jobs(
        self, *, worker: WorkerIdentity, limit: int, lease_seconds: int
    ) -> tuple[JobLease, ...]:
        del worker, limit, lease_seconds
        leases, self.leases = self.leases, ()
        return leases

    def renew_lease(
        self, *, lease: JobLease, worker_id: UUID, lease_seconds: int
    ) -> bool:
        del lease, worker_id, lease_seconds
        self.renewed.set()
        return self.renew_result

    def complete_job(
        self,
        *,
        lease: JobLease,
        worker_id: UUID,
        result: JobResult,
        metrics: dict[str, object],
    ) -> str:
        del lease, worker_id, metrics
        self.completed.append(result)
        return "succeeded"

    def fail_job(
        self,
        *,
        lease: JobLease,
        worker_id: UUID,
        error_code: str,
        error_message: str,
        retryable: bool,
        ambiguous: bool,
        metrics: dict[str, object],
    ) -> str:
        del lease, worker_id, error_message, metrics
        self.failures.append((error_code, retryable, ambiguous))
        return "retry_scheduled" if retryable else "review_required"

    def heartbeat(self, *, worker: WorkerIdentity, current_job_id: UUID | None) -> None:
        del worker
        self.heartbeats.append(current_job_id)

    def deliver_outbox(self, *, lease: JobLease) -> JobResult:
        del lease
        return JobResult(values={"delivered": True})


def runner(
    store: FakeDurableStore,
    handler: object,
    events: list[dict[str, object]],
    *,
    renewal_seconds: float = 60,
) -> DurableWorker:
    def invoke(value: JobLease) -> JobResult:
        assert callable(handler)
        result = handler(value)
        assert isinstance(result, JobResult)
        return result

    return DurableWorker(
        store=store,
        worker=WorkerIdentity(
            worker_id=WORKER_ID,
            instance_name="test-worker",
            build_commit="test-commit",
            environment="test",
        ),
        handlers={"interpretation.run": invoke},
        batch_size=4,
        lease_seconds=120,
        renewal_seconds=renewal_seconds,
        emit=events.append,
    )


def test_worker_completes_a_leased_job_and_records_safe_metrics() -> None:
    store = FakeDurableStore()
    events: list[dict[str, object]] = []
    result = JobResult(values={"request_id": str(REQUEST_ID), "status": "interpreted"})

    cycle = runner(store, lambda _lease: result, events).run_once()

    assert cycle.leased == 1
    assert cycle.succeeded == 1
    assert cycle.lease_lost == 0
    assert store.completed == [result]
    assert store.heartbeats == [None, JOB_ID, None]
    assert [event["event"] for event in events] == ["job.started", "job.finished"]


def test_worker_sanitizes_unexpected_handler_failures() -> None:
    store = FakeDurableStore()
    events: list[dict[str, object]] = []

    def fail(_lease: JobLease) -> JobResult:
        raise RuntimeError("provider-secret-must-not-leak")

    cycle = runner(store, fail, events).run_once()

    assert cycle.retry_scheduled == 1
    assert store.failures == [("unexpected_handler_error", True, False)]
    assert "provider-secret-must-not-leak" not in str(events)


def test_worker_never_commits_after_lease_renewal_is_lost() -> None:
    store = FakeDurableStore(renew_result=False)
    events: list[dict[str, object]] = []

    def wait_for_renewal(_lease: JobLease) -> JobResult:
        assert store.renewed.wait(timeout=1)
        return JobResult(values={"status": "would-have-completed"})

    cycle = runner(store, wait_for_renewal, events, renewal_seconds=0.001).run_once()

    assert cycle.lease_lost == 1
    assert store.completed == []
    assert any(event["event"] == "job.lease_lost" for event in events)


def test_worker_without_server_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(worker_main, "get_settings", lambda: Settings())

    assert worker_main.main(["--once"]) == 2
    captured = capsys.readouterr()
    assert '"event":"worker.configuration_invalid"' in captured.out


def test_worker_status_contains_no_secret_configuration() -> None:
    status = worker_main.worker_status(
        Settings(
            database_url=SecretStr("postgresql://user:secret@localhost/db"),
            gemini_api_key=SecretStr("secret"),
        ),
        durable_schema_ready=True,
    )
    assert "secret" not in str(status)
    assert status["queue_consumer_enabled"] is True


def test_worker_once_reports_transient_store_outage_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ReadyStore:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def ready(self) -> bool:
            return True

    class UnavailableWorker:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run_once(self) -> None:
            raise DurableStoreError("database-secret-must-not-leak")

    monkeypatch.setattr(
        worker_main,
        "get_settings",
        lambda: Settings.model_validate(
            {"database_url": SecretStr("postgresql://user:secret@localhost/db")}
        ),
    )
    monkeypatch.setattr(worker_main, "PostgresDurableStore", ReadyStore)
    monkeypatch.setattr(worker_main, "DurableWorker", UnavailableWorker)
    monkeypatch.setattr(worker_main, "build_handlers", lambda *_args: {})

    assert worker_main.main(["--once"]) == 3
    captured = capsys.readouterr()
    assert '"event":"worker.store_unavailable"' in captured.out
    assert '"retry_seconds":1.0' in captured.out
    assert "database-secret-must-not-leak" not in captured.out
    assert captured.err == ""
