from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import replace
from time import monotonic

from coordination.durable.contracts import JobLease, JobResult, WorkerCycle, WorkerIdentity
from coordination.durable.persistence import DurableStore, DurableStoreError, JobStateConflictError


class RetryableJobError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PermanentJobError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AmbiguousJobOutcomeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JobHandler:
    def __call__(self, lease: JobLease) -> JobResult:  # pragma: no cover - protocol shape
        raise NotImplementedError


class _LeaseRenewal(AbstractContextManager["_LeaseRenewal"]):
    def __init__(
        self,
        *,
        renew: Callable[[], bool],
        interval_seconds: float,
    ) -> None:
        self._renew = renew
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self.lost = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _LeaseRenewal:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval_seconds + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                if not self._renew():
                    self.lost.set()
                    return
            except DurableStoreError:
                # Losing contact with the lease store is equivalent to losing the lease.
                self.lost.set()
                return


class DurableWorker:
    def __init__(
        self,
        *,
        store: DurableStore,
        worker: WorkerIdentity,
        handlers: Mapping[str, Callable[[JobLease], JobResult]],
        batch_size: int,
        lease_seconds: int,
        renewal_seconds: float,
        emit: Callable[[dict[str, object]], None],
    ) -> None:
        self._store = store
        self._worker = worker
        self._handlers = handlers
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._renewal_seconds = renewal_seconds
        self._emit = emit

    def run_once(self) -> WorkerCycle:
        self._store.heartbeat(worker=self._worker, current_job_id=None)
        leases = self._store.lease_jobs(
            worker=self._worker,
            limit=self._batch_size,
            lease_seconds=self._lease_seconds,
        )
        cycle = WorkerCycle(leased=len(leases))
        for lease in leases:
            outcome = self._run_job(lease)
            cycle = _record_cycle_outcome(cycle, outcome)
        self._store.heartbeat(worker=self._worker, current_job_id=None)
        return cycle

    def _run_job(self, lease: JobLease) -> str:
        started = monotonic()
        self._store.heartbeat(worker=self._worker, current_job_id=lease.job_id)
        self._emit(
            {
                "event": "job.started",
                "job_id": str(lease.job_id),
                "job_kind": lease.job_kind,
                "attempt": lease.attempt_count,
                "correlation_id": str(lease.correlation_id),
            }
        )
        handler = self._handlers.get(lease.job_kind)
        if handler is None:
            return self._record_failure(
                lease,
                code="unsupported_job_kind",
                retryable=False,
                ambiguous=False,
                started=started,
            )

        renewal = _LeaseRenewal(
            renew=lambda: self._store.renew_lease(
                lease=lease,
                worker_id=self._worker.worker_id,
                lease_seconds=self._lease_seconds,
            ),
            interval_seconds=self._renewal_seconds,
        )
        try:
            with renewal:
                result = handler(lease)
            if renewal.lost.is_set():
                self._emit(
                    {
                        "event": "job.lease_lost",
                        "job_id": str(lease.job_id),
                        "job_kind": lease.job_kind,
                    }
                )
                return "lease_lost"
            state = self._store.complete_job(
                lease=lease,
                worker_id=self._worker.worker_id,
                result=result,
                metrics={"runtime_ms": _runtime_ms(started)},
            )
        except RetryableJobError as error:
            state = self._record_failure(
                lease,
                code=error.code,
                retryable=True,
                ambiguous=False,
                started=started,
            )
        except PermanentJobError as error:
            state = self._record_failure(
                lease,
                code=error.code,
                retryable=False,
                ambiguous=False,
                started=started,
            )
        except AmbiguousJobOutcomeError as error:
            state = self._record_failure(
                lease,
                code=error.code,
                retryable=False,
                ambiguous=True,
                started=started,
            )
        except JobStateConflictError:
            state = "lease_lost"
        except Exception:
            state = self._record_failure(
                lease,
                code="unexpected_handler_error",
                retryable=True,
                ambiguous=False,
                started=started,
            )

        self._emit(
            {
                "event": "job.finished",
                "job_id": str(lease.job_id),
                "job_kind": lease.job_kind,
                "state": state,
                "runtime_ms": _runtime_ms(started),
            }
        )
        if state in {
            "succeeded",
            "retry_scheduled",
            "dead_letter",
            "review_required",
            "cancelled",
            "lease_lost",
        }:
            return state
        return "review_required"

    def _record_failure(
        self,
        lease: JobLease,
        *,
        code: str,
        retryable: bool,
        ambiguous: bool,
        started: float,
    ) -> str:
        try:
            return self._store.fail_job(
                lease=lease,
                worker_id=self._worker.worker_id,
                error_code=code,
                error_message=code,
                retryable=retryable,
                ambiguous=ambiguous,
                metrics={"runtime_ms": _runtime_ms(started)},
            )
        except JobStateConflictError:
            return "lease_lost"


def _runtime_ms(started: float) -> int:
    return max(0, int((monotonic() - started) * 1000))


def _record_cycle_outcome(cycle: WorkerCycle, outcome: str) -> WorkerCycle:
    if outcome == "succeeded":
        return replace(cycle, succeeded=cycle.succeeded + 1)
    if outcome == "retry_scheduled":
        return replace(cycle, retry_scheduled=cycle.retry_scheduled + 1)
    if outcome == "dead_letter":
        return replace(cycle, dead_letter=cycle.dead_letter + 1)
    if outcome == "cancelled":
        return replace(cycle, cancelled=cycle.cancelled + 1)
    if outcome == "lease_lost":
        return replace(cycle, lease_lost=cycle.lease_lost + 1)
    return replace(cycle, review_required=cycle.review_required + 1)
