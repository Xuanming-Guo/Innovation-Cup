from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction, worker_transaction
from coordination.durable.contracts import (
    JobKind,
    JobLease,
    JobResult,
    JobView,
    NotificationPage,
    NotificationView,
    QueueMetrics,
    WorkerIdentity,
)


class DurableStoreError(RuntimeError):
    """Durable coordination state could not be read or changed safely."""


class JobNotFoundError(LookupError):
    """No authorised durable job exists."""


class JobStateConflictError(ValueError):
    """A lease, cancellation or terminal-state precondition changed."""


class JobIdempotencyConflictError(ValueError):
    """A durable command key was reused with different contents."""


class NotificationNotFoundError(LookupError):
    """No notification exists for the current recipient."""


class DurableStore(Protocol):
    def lease_jobs(
        self, *, worker: WorkerIdentity, limit: int, lease_seconds: int
    ) -> tuple[JobLease, ...]: ...

    def renew_lease(
        self, *, lease: JobLease, worker_id: UUID, lease_seconds: int
    ) -> bool: ...

    def complete_job(
        self,
        *,
        lease: JobLease,
        worker_id: UUID,
        result: JobResult,
        metrics: dict[str, object],
    ) -> str: ...

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
    ) -> str: ...

    def heartbeat(
        self, *, worker: WorkerIdentity, current_job_id: UUID | None
    ) -> None: ...

    def deliver_outbox(self, *, lease: JobLease) -> JobResult: ...


class PostgresDurableStore:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _worker_transaction(self, purpose: str) -> AbstractContextManager[Any]:
        return worker_transaction(
            self._dsn,
            purpose=purpose,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def _company_transaction(
        self, context: CompanyContext, purpose: str
    ) -> AbstractContextManager[Any]:
        return company_transaction(
            self._dsn,
            role="coordination_api",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            purpose=purpose,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def ready(self) -> bool:
        try:
            with self._worker_transaction("durable:ready") as connection:
                row = connection.execute(
                    "select to_regprocedure("
                    "'app.lease_durable_jobs(uuid,integer,integer)') is not null "
                    "and has_function_privilege("
                    "'app.lease_durable_jobs(uuid,integer,integer)', 'EXECUTE') as ready"
                ).fetchone()
        except psycopg.Error as error:
            raise DurableStoreError("durable schema readiness could not be checked") from error
        return bool(row and row["ready"])

    def lease_jobs(
        self, *, worker: WorkerIdentity, limit: int, lease_seconds: int
    ) -> tuple[JobLease, ...]:
        try:
            with self._worker_transaction("durable:lease") as connection:
                rows = connection.execute(
                    "select * from app.lease_durable_jobs(%s, %s, %s)",
                    (worker.worker_id, limit, lease_seconds),
                ).fetchall()
        except psycopg.Error as error:
            raise DurableStoreError("durable jobs could not be leased") from error
        return tuple(JobLease.model_validate(dict(row)) for row in rows)

    def renew_lease(
        self, *, lease: JobLease, worker_id: UUID, lease_seconds: int
    ) -> bool:
        try:
            with self._worker_transaction("durable:renew") as connection:
                row = connection.execute(
                    "select app.renew_durable_job_lease(%s, %s, %s, %s, %s) as renewed",
                    (
                        lease.company_id,
                        lease.job_id,
                        worker_id,
                        lease.lease_token,
                        lease_seconds,
                    ),
                ).fetchone()
        except psycopg.Error as error:
            raise DurableStoreError("durable job lease could not be renewed") from error
        return bool(row and row["renewed"])

    def complete_job(
        self,
        *,
        lease: JobLease,
        worker_id: UUID,
        result: JobResult,
        metrics: dict[str, object],
    ) -> str:
        try:
            with self._worker_transaction("durable:complete") as connection:
                row = connection.execute(
                    "select * from app.complete_durable_job(%s, %s, %s, %s, %s, %s, %s)",
                    (
                        lease.company_id,
                        lease.job_id,
                        worker_id,
                        lease.lease_token,
                        Jsonb(result.values),
                        result.digest,
                        Jsonb(metrics),
                    ),
                ).fetchone()
        except psycopg.errors.SerializationFailure as error:
            raise JobStateConflictError("durable job lease changed") from error
        except psycopg.Error as error:
            raise DurableStoreError("durable job completion could not be recorded") from error
        if row is None:
            raise DurableStoreError("durable job completion returned no state")
        return cast(str, row["job_state"])

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
        try:
            with self._worker_transaction("durable:fail") as connection:
                row = connection.execute(
                    "select * from app.fail_durable_job(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        lease.company_id,
                        lease.job_id,
                        worker_id,
                        lease.lease_token,
                        error_code,
                        error_message[:1000],
                        retryable,
                        ambiguous,
                        Jsonb(metrics),
                    ),
                ).fetchone()
        except psycopg.errors.SerializationFailure as error:
            raise JobStateConflictError("durable job lease changed") from error
        except psycopg.Error as error:
            raise DurableStoreError("durable job failure could not be recorded") from error
        if row is None:
            raise DurableStoreError("durable job failure returned no state")
        return cast(str, row["job_state"])

    def heartbeat(self, *, worker: WorkerIdentity, current_job_id: UUID | None) -> None:
        try:
            with self._worker_transaction("durable:heartbeat") as connection:
                connection.execute(
                    "select app.record_worker_heartbeat(%s, %s, %s, %s, %s)",
                    (
                        worker.worker_id,
                        worker.instance_name,
                        worker.build_commit,
                        worker.environment,
                        current_job_id,
                    ),
                )
        except psycopg.Error as error:
            raise DurableStoreError("worker heartbeat could not be recorded") from error

    def deliver_outbox(self, *, lease: JobLease) -> JobResult:
        try:
            with self._worker_transaction("outbox:deliver") as connection:
                row = connection.execute(
                    "select * from app.deliver_internal_outbox_intent(%s, %s, %s, %s)",
                    (
                        lease.company_id,
                        lease.aggregate_id,
                        lease.job_id,
                        lease.lease_token,
                    ),
                ).fetchone()
        except psycopg.errors.SerializationFailure as error:
            raise JobStateConflictError("outbox delivery lease changed") from error
        except psycopg.Error as error:
            raise DurableStoreError("outbox delivery could not be recorded") from error
        if row is None:
            raise DurableStoreError("outbox delivery returned no result")
        return JobResult(
            values={
                "outbox_intent_id": str(lease.aggregate_id),
                "notification_count": int(row["notification_count"]),
                "replayed": bool(row["replayed"]),
            }
        )

    def ensure_job(
        self,
        *,
        context: CompanyContext,
        job_kind: JobKind,
        aggregate_id: UUID,
        idempotency_key: str,
        command_digest: bytes,
        correlation_id: UUID,
    ) -> JobView:
        try:
            with self._company_transaction(context, "durable:enqueue") as connection:
                row = connection.execute(
                    "select * from app.ensure_durable_job(%s, %s, %s, %s, %s, %s)",
                    (
                        context.company_id,
                        job_kind,
                        aggregate_id,
                        idempotency_key,
                        command_digest,
                        correlation_id,
                    ),
                ).fetchone()
        except psycopg.errors.UniqueViolation as error:
            raise JobIdempotencyConflictError("job idempotency key conflicts") from error
        except psycopg.errors.InsufficientPrivilege as error:
            raise PermissionError("manager authority is required") from error
        except psycopg.errors.InvalidParameterValue as error:
            raise JobNotFoundError("planning request was not found") from error
        except psycopg.Error as error:
            raise DurableStoreError("durable job could not be ensured") from error
        if row is None:
            raise DurableStoreError("durable job ensure returned no state")
        return _job_view(row)

    def get_job(self, *, context: CompanyContext, job_id: UUID) -> JobView:
        try:
            with self._company_transaction(context, "durable:read") as connection:
                row = connection.execute(
                    """
                    select id as job_id, job_kind, aggregate_id, state, attempt_count,
                           max_attempts, available_at, leased_until,
                           cancel_requested_at is not null as cancellation_requested,
                           last_error_code, created_at, completed_at
                    from app.durable_jobs where company_id = %s and id = %s
                    """,
                    (context.company_id, job_id),
                ).fetchone()
        except psycopg.Error as error:
            raise DurableStoreError("durable job could not be read") from error
        if row is None:
            raise JobNotFoundError("job was not found")
        return _job_view(row)

    def cancel_job(
        self,
        *,
        context: CompanyContext,
        job_id: UUID,
        reason: str,
        idempotency_key: str,
        command_digest: bytes,
    ) -> JobView:
        try:
            with self._company_transaction(context, "durable:cancel") as connection:
                row = connection.execute(
                    "select * from app.request_durable_job_cancellation(%s, %s, %s, %s, %s)",
                    (
                        context.company_id,
                        job_id,
                        reason,
                        idempotency_key,
                        command_digest,
                    ),
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise PermissionError("manager authority is required") from error
        except psycopg.errors.SerializationFailure as error:
            raise JobStateConflictError("job cancellation conflicts with current state") from error
        except psycopg.Error as error:
            raise DurableStoreError("job cancellation could not be stored") from error
        if row is None:
            raise JobNotFoundError("job was not found")
        return _job_view(row)

    def retry_job(
        self,
        *,
        context: CompanyContext,
        job_id: UUID,
        reason: str,
        idempotency_key: str,
        command_digest: bytes,
    ) -> JobView:
        try:
            with self._company_transaction(context, "durable:retry") as connection:
                row = connection.execute(
                    "select * from app.retry_durable_planning_job(%s, %s, %s, %s, %s)",
                    (
                        context.company_id,
                        job_id,
                        reason,
                        idempotency_key,
                        command_digest,
                    ),
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise PermissionError("manager authority is required") from error
        except psycopg.errors.InvalidParameterValue as error:
            if "job_not_found" in str(error):
                raise JobNotFoundError("job was not found") from error
            raise JobStateConflictError("job retry request is invalid") from error
        except (
            psycopg.errors.SerializationFailure,
            psycopg.errors.UniqueViolation,
        ) as error:
            raise JobStateConflictError("job retry conflicts with current state") from error
        except psycopg.Error as error:
            raise DurableStoreError("durable job retry could not be stored") from error
        if row is None:
            raise JobNotFoundError("job was not found")
        return _job_view(row)

    def metrics(self, *, context: CompanyContext) -> QueueMetrics:
        try:
            with self._company_transaction(context, "durable:metrics") as connection:
                row = connection.execute(
                    "select * from app.company_durable_metrics(%s)",
                    (context.company_id,),
                ).fetchone()
        except psycopg.errors.InsufficientPrivilege as error:
            raise PermissionError("manager authority is required") from error
        except psycopg.Error as error:
            raise DurableStoreError("durable metrics could not be read") from error
        if row is None:
            raise DurableStoreError("durable metrics returned no state")
        return QueueMetrics.model_validate(dict(row))

    def list_notifications(
        self,
        *,
        context: CompanyContext,
        after_created_at: datetime | None,
        after_id: UUID | None,
        limit: int,
    ) -> NotificationPage:
        try:
            with self._company_transaction(context, "notification:list") as connection:
                rows = connection.execute(
                    """
                    select id as notification_id, message_key, subject_type, subject_id,
                           safe_parameters, created_at, delivered_at, seen_at, acknowledged_at
                    from app.notifications
                    where company_id = %s
                      and recipient_membership_id = %s
                      and (%s::timestamptz is null or (created_at, id) > (%s, %s::uuid))
                    order by created_at, id
                    limit %s
                    """,
                    (
                        context.company_id,
                        context.membership_id,
                        after_created_at,
                        after_created_at,
                        after_id,
                        limit + 1,
                    ),
                ).fetchall()
                visible = rows[:limit]
                if visible:
                    delivered = connection.execute(
                        """
                        update app.notifications
                        set delivered_at = coalesce(delivered_at, clock_timestamp())
                        where company_id = %s and recipient_membership_id = %s
                          and id = any(%s)
                        returning id as notification_id, message_key, subject_type,
                                  subject_id, safe_parameters, created_at, delivered_at,
                                  seen_at, acknowledged_at
                        """,
                        (
                            context.company_id,
                            context.membership_id,
                            [row["notification_id"] for row in visible],
                        ),
                    ).fetchall()
                    delivered_by_id = {
                        row["notification_id"]: row for row in delivered
                    }
                    visible = [
                        delivered_by_id.get(row["notification_id"], row)
                        for row in visible
                    ]
        except psycopg.Error as error:
            raise DurableStoreError("notifications could not be read") from error
        notifications = tuple(NotificationView.model_validate(dict(row)) for row in visible)
        next_cursor = None
        if len(rows) > limit and notifications:
            tail = notifications[-1]
            next_cursor = f"{tail.created_at.isoformat()}|{tail.notification_id}"
        return NotificationPage(notifications=notifications, next_cursor=next_cursor)

    def advance_notification(
        self, *, context: CompanyContext, notification_id: UUID, action: str
    ) -> NotificationView:
        if action not in {"seen", "acknowledged"}:
            raise ValueError("unsupported notification action")
        try:
            with self._company_transaction(context, f"notification:{action}") as connection:
                row = connection.execute(
                    "select * from app.advance_notification_state(%s, %s, %s)",
                    (context.company_id, notification_id, action),
                ).fetchone()
        except psycopg.Error as error:
            raise DurableStoreError("notification state could not be advanced") from error
        if row is None:
            raise NotificationNotFoundError("notification was not found")
        return NotificationView.model_validate(dict(row))


def _job_view(row: Any) -> JobView:
    return JobView.model_validate(dict(row))
