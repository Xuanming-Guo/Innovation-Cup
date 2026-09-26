from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from coordination.auth.models import AuthenticatedUser, CompanyContext

JobKind = Literal[
    "interpretation.run",
    "planning.materialize",
    "planning.run",
    "private_file.scan",
    "outbox.deliver",
]
JobState = Literal[
    "queued",
    "leased",
    "retry_scheduled",
    "succeeded",
    "dead_letter",
    "review_required",
    "cancelled",
]


class StrictDurableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobLease(StrictDurableModel):
    job_id: UUID
    company_id: UUID
    job_kind: JobKind
    aggregate_id: UUID
    payload: dict[str, Any]
    requested_by_membership_id: UUID | None
    requested_by_user_id: UUID | None
    administrative_role: Literal["member", "manager", "company_admin"] | None
    employee_id: UUID | None
    correlation_id: UUID
    attempt_count: int
    max_attempts: int
    lease_token: UUID
    leased_until: datetime

    def company_context(self) -> CompanyContext:
        if (
            self.requested_by_membership_id is None
            or self.requested_by_user_id is None
            or self.administrative_role is None
        ):
            raise ValueError("job does not have an active requesting membership")
        return CompanyContext(
            actor=AuthenticatedUser(
                user_id=self.requested_by_user_id,
                role="authenticated",
                session_id=self.job_id,
                assurance_level="aal2",
            ),
            company_id=self.company_id,
            membership_id=self.requested_by_membership_id,
            administrative_role=self.administrative_role,
            employee_id=self.employee_id,
        )


class JobResult(StrictDurableModel):
    values: dict[str, Any]

    @property
    def digest(self) -> bytes:
        encoded = json.dumps(
            self.values,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).digest()


class JobView(StrictDurableModel):
    job_id: UUID
    job_kind: JobKind
    aggregate_id: UUID
    state: JobState
    attempt_count: int
    max_attempts: int
    available_at: datetime
    leased_until: datetime | None
    cancellation_requested: bool
    last_error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class QueueMetrics(StrictDurableModel):
    queued: int
    leased: int
    retry_scheduled: int
    dead_letter: int
    review_required: int
    cancelled: int
    succeeded: int
    oldest_ready_seconds: int | None
    outbox_pending: int
    notifications_unread: int


class NotificationView(StrictDurableModel):
    notification_id: UUID
    message_key: str
    subject_type: str
    subject_id: UUID
    safe_parameters: dict[str, Any]
    created_at: datetime
    delivered_at: datetime | None
    seen_at: datetime | None
    acknowledged_at: datetime | None


class NotificationPage(StrictDurableModel):
    notifications: tuple[NotificationView, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    worker_id: UUID
    instance_name: str
    build_commit: str
    environment: str


@dataclass(frozen=True, slots=True)
class WorkerCycle:
    leased: int = 0
    succeeded: int = 0
    retry_scheduled: int = 0
    dead_letter: int = 0
    review_required: int = 0
    cancelled: int = 0
    lease_lost: int = 0
