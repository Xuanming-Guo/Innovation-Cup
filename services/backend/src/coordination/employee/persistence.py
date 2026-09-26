from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, NoReturn, Protocol
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.db.session import company_transaction
from coordination.employee.contracts import (
    ApprovedBrief,
    EmployeeTask,
    ReviewCommand,
    ReviewPolicyCommand,
    ReviewPolicyResult,
    ReviewResult,
    SubmissionCommand,
    SubmissionFile,
    SubmissionResult,
    SubmissionReviewView,
    TaskTransitionCommand,
    TaskTransitionResult,
    TaskView,
)


class EmployeeStoreError(RuntimeError):
    """The employee workflow store is unavailable."""


class EmployeeTaskNotFoundError(LookupError):
    """The task or submission is absent from the actor's authorised view."""


class EmployeeAuthorityError(PermissionError):
    """The actor does not hold the required task or review relationship."""


class EmployeeStateConflictError(ValueError):
    """The command is invalid for the current exact lifecycle version."""


class EmployeeIdempotencyConflictError(ValueError):
    """An idempotency key identifies a different employee command."""


class EmployeeStore(Protocol):
    def list_tasks(
        self, *, context: CompanyContext, view: TaskView
    ) -> tuple[EmployeeTask, ...]: ...

    def transition(
        self, *, context: CompanyContext, task_id: UUID, command: TaskTransitionCommand
    ) -> TaskTransitionResult: ...

    def set_review_policy(
        self, *, context: CompanyContext, task_id: UUID, command: ReviewPolicyCommand
    ) -> ReviewPolicyResult: ...

    def submit(
        self, *, context: CompanyContext, task_id: UUID, command: SubmissionCommand
    ) -> SubmissionResult: ...

    def get_submission(
        self, *, context: CompanyContext, submission_id: UUID
    ) -> SubmissionReviewView: ...

    def list_pending_reviews(
        self, *, context: CompanyContext
    ) -> tuple[SubmissionReviewView, ...]: ...

    def review(
        self, *, context: CompanyContext, submission_id: UUID, command: ReviewCommand
    ) -> ReviewResult: ...


class PostgresEmployeeStore:
    def __init__(self, dsn: str, *, connect_timeout_seconds: int = 5) -> None:
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _transaction(self, context: CompanyContext, purpose: str) -> AbstractContextManager[Any]:
        return company_transaction(
            self._dsn,
            role="coordination_api",
            actor_id=context.actor.user_id,
            company_id=context.company_id,
            purpose=purpose,
            connect_timeout_seconds=self._connect_timeout_seconds,
        )

    def list_tasks(self, *, context: CompanyContext, view: TaskView) -> tuple[EmployeeTask, ...]:
        if context.employee_id is None:
            raise EmployeeAuthorityError("an active employee profile is required")
        filters = {
            "today": "item.status in ('assigned', 'acknowledged', 'in_progress') "
            "and item.start_at < date_trunc('day', clock_timestamp()) + interval '1 day' "
            "and item.finish_at >= date_trunc('day', clock_timestamp())",
            "upcoming": "item.status in ('assigned', 'acknowledged') "
            "and item.start_at >= date_trunc('day', clock_timestamp()) + interval '1 day'",
            "blocked": "item.status = 'blocked'",
            "submitted": "item.status in ('submitted', 'revision_requested', 'accepted')",
        }
        try:
            with self._transaction(context, "employee:task-list") as connection:
                rows = connection.execute(
                    f"""
                    select item.task_id, item.task_key, item.title, item.scheduling_kind,
                           item.status, item.row_version, item.start_at, item.finish_at,
                           app.task_reviewer_display_name(
                             app.current_actor_id(), item.company_id,
                             coalesce(latest_submission.review_policy_id, review_policy.id)
                           ) as reviewer_name,
                           latest_submission.id as latest_submission_id,
                           latest_submission.version as latest_submission_version,
                           brief.id as brief_id, brief.version as brief_version,
                           brief.brief_payload
                    from app.work_items as item
                    join app.work_assignments as assignment
                      on assignment.company_id = item.company_id
                     and assignment.task_id = item.task_id
                     and assignment.active and assignment.assignment_role = 'owner'
                    join app.execution_resources as resource
                      on resource.company_id = assignment.company_id
                     and resource.id = assignment.resource_id
                     and resource.status = 'active'
                    left join lateral (
                      select submission.id, submission.version, submission.review_policy_id
                      from app.submissions as submission
                      where submission.company_id = item.company_id
                        and submission.task_id = item.task_id
                      order by submission.version desc limit 1
                    ) as latest_submission on true
                    left join app.task_review_policies as review_policy
                      on review_policy.company_id = item.company_id
                     and review_policy.task_id = item.task_id and review_policy.active
                    left join lateral (
                      select candidate.id, candidate.version, candidate.brief_payload
                      from app.employee_brief_versions as candidate
                      where candidate.company_id = item.company_id
                        and candidate.id = item.employee_brief_version_id
                        and app.can_read_employee_brief(
                          app.current_actor_id(), candidate.company_id, candidate.id
                        )
                      limit 1
                    ) as brief on true
                    where item.company_id = %s and resource.employee_id = %s
                      and {filters[view]}
                    order by item.start_at, item.task_key
                    """,
                    (context.company_id, context.employee_id),
                ).fetchall()
                return tuple(
                    EmployeeTask(
                        task_id=row["task_id"],
                        task_key=row["task_key"],
                        title=row["title"],
                        scheduling_kind=row["scheduling_kind"],
                        status=row["status"],
                        row_version=row["row_version"],
                        start_at=row["start_at"],
                        finish_at=row["finish_at"],
                        reviewer_name=row["reviewer_name"],
                        latest_submission_id=row["latest_submission_id"],
                        latest_submission_version=row["latest_submission_version"],
                        approved_brief=ApprovedBrief(
                            brief_version_id=row["brief_id"],
                            version=row["brief_version"],
                            content=row["brief_payload"],
                        )
                        if row["brief_id"] is not None
                        else None,
                    )
                    for row in rows
                )
        except psycopg.Error as error:
            raise EmployeeStoreError("employee tasks could not be loaded") from error

    def transition(
        self, *, context: CompanyContext, task_id: UUID, command: TaskTransitionCommand
    ) -> TaskTransitionResult:
        try:
            with self._transaction(context, "employee:transition") as connection:
                row = connection.execute(
                    """
                    select * from app.transition_employee_task(
                      %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        task_id,
                        command.command,
                        command.expected_task_version,
                        Jsonb(command.payload),
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise EmployeeStoreError("task transition returned no result")
                return TaskTransitionResult(
                    event_id=row["event_id"],
                    task_status=row["task_status"],
                    task_version=row["task_version"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    def set_review_policy(
        self, *, context: CompanyContext, task_id: UUID, command: ReviewPolicyCommand
    ) -> ReviewPolicyResult:
        try:
            with self._transaction(context, "employee:review-policy") as connection:
                row = connection.execute(
                    """
                    select * from app.set_task_review_policy(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        task_id,
                        command.reviewer_employee_id,
                        command.self_certifiable,
                        command.self_certification_rule,
                        command.expected_task_version,
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise EmployeeStoreError("review policy returned no result")
                return ReviewPolicyResult(
                    policy_id=row["policy_id"],
                    version=row["policy_version"],
                    task_version=row["task_version"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    def submit(
        self, *, context: CompanyContext, task_id: UUID, command: SubmissionCommand
    ) -> SubmissionResult:
        try:
            with self._transaction(context, "employee:submit") as connection:
                row = connection.execute(
                    """
                    select * from app.submit_employee_task(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        task_id,
                        command.narrative,
                        Jsonb(list(command.external_evidence_refs)),
                        Jsonb([str(value) for value in command.file_ids]),
                        command.reported_active_minutes,
                        command.expected_task_version,
                        bytes.fromhex(command.submission_digest),
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise EmployeeStoreError("submission returned no result")
                return SubmissionResult(
                    submission_id=row["submission_id"],
                    version=row["submission_version"],
                    state=row["submission_state"],
                    task_version=row["task_version"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    def get_submission(
        self, *, context: CompanyContext, submission_id: UUID
    ) -> SubmissionReviewView:
        try:
            with self._transaction(context, "employee:submission-review") as connection:
                row = connection.execute(
                    """
                    select submission.id, submission.task_id, item.title as task_title,
                           submission.version, submission.state, submission.narrative,
                           submission.external_evidence_refs,
                           encode(submission.submission_digest, 'hex') as submission_digest,
                           submission.submitting_employee_id,
                           app.task_employee_display_name(
                             app.current_actor_id(), submission.company_id,
                             submission.task_id, submission.submitting_employee_id
                           ) as submitting_employee_name,
                           policy.version as review_policy_version,
                           submission.submitted_at,
                           coalesce(files.items, '[]'::jsonb) as files
                    from app.submissions as submission
                    join app.work_items as item
                      on item.company_id = submission.company_id
                     and item.task_id = submission.task_id
                    join app.task_review_policies as policy
                      on policy.company_id = submission.company_id
                     and policy.id = submission.review_policy_id
                    left join lateral (
                      select jsonb_agg(jsonb_build_object(
                        'file_id', file.id,
                        'display_filename', file.display_filename,
                        'detected_mime_type', file.detected_mime_type,
                        'size_bytes', file.size_bytes,
                        'content_sha256', encode(file.content_sha256, 'hex')
                      ) order by file.display_filename, file.id) as items
                      from app.submission_files as linked
                      join app.private_files as file
                        on file.company_id = linked.company_id
                       and file.id = linked.file_id
                       and file.state = 'available' and file.scan_state = 'clean'
                      where linked.company_id = submission.company_id
                        and linked.submission_id = submission.id
                    ) as files on true
                    where submission.company_id = %s and submission.id = %s
                    """,
                    (context.company_id, submission_id),
                ).fetchone()
                if row is None or row["submitting_employee_name"] is None:
                    raise EmployeeTaskNotFoundError("submission was not found")
                return SubmissionReviewView(
                    submission_id=row["id"],
                    task_id=row["task_id"],
                    task_title=row["task_title"],
                    version=row["version"],
                    state=row["state"],
                    narrative=row["narrative"],
                    external_evidence_refs=tuple(row["external_evidence_refs"]),
                    submission_digest=row["submission_digest"],
                    submitting_employee_id=row["submitting_employee_id"],
                    submitting_employee_name=row["submitting_employee_name"],
                    review_policy_version=row["review_policy_version"],
                    submitted_at=row["submitted_at"],
                    files=tuple(SubmissionFile.model_validate(value) for value in row["files"]),
                )
        except EmployeeTaskNotFoundError:
            raise
        except psycopg.Error as error:
            raise EmployeeStoreError("submission could not be loaded") from error

    def list_pending_reviews(
        self, *, context: CompanyContext
    ) -> tuple[SubmissionReviewView, ...]:
        if context.employee_id is None:
            raise EmployeeAuthorityError("an active reviewer profile is required")
        try:
            with self._transaction(context, "employee:pending-reviews") as connection:
                rows = connection.execute(
                    """
                    select submission.id
                    from app.submissions as submission
                    join app.task_review_policies as policy
                      on policy.company_id = submission.company_id
                     and policy.id = submission.review_policy_id
                    where submission.company_id = %s
                      and submission.state = 'submitted'
                      and policy.reviewer_employee_id = %s
                    order by submission.submitted_at, submission.id
                    """,
                    (context.company_id, context.employee_id),
                ).fetchall()
        except psycopg.Error as error:
            raise EmployeeStoreError("pending reviews could not be loaded") from error
        return tuple(
            self.get_submission(context=context, submission_id=row["id"])
            for row in rows
        )

    def review(
        self, *, context: CompanyContext, submission_id: UUID, command: ReviewCommand
    ) -> ReviewResult:
        try:
            with self._transaction(context, "employee:review") as connection:
                row = connection.execute(
                    """
                    select * from app.review_task_submission(
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        context.company_id,
                        submission_id,
                        command.expected_submission_version,
                        bytes.fromhex(command.submission_digest),
                        command.decision,
                        Jsonb(list(command.criterion_findings)),
                        command.correction_request,
                        command.idempotency_key,
                        bytes.fromhex(command.digest),
                        command.correlation_id,
                    ),
                ).fetchone()
                if row is None:
                    raise EmployeeStoreError("submission review returned no result")
                return ReviewResult(
                    review_id=row["review_id"],
                    decision=row["review_decision"],
                    task_status=row["task_status"],
                    task_version=row["task_version"],
                    replayed=row["replayed"],
                )
        except psycopg.Error as error:
            self._translate(error)

    @staticmethod
    def _translate(error: psycopg.Error) -> NoReturn:
        message = str(error)
        if error.sqlstate == "P0002" or "not_found" in message:
            raise EmployeeTaskNotFoundError("task resource was not found") from error
        if error.sqlstate == "42501":
            raise EmployeeAuthorityError("task or reviewer authority is required") from error
        if error.sqlstate == "23505" or "idempotency" in message:
            raise EmployeeIdempotencyConflictError("idempotency key was reused") from error
        if error.sqlstate in ("22023", "40001") or "stale" in message:
            raise EmployeeStateConflictError("employee workflow state changed") from error
        raise EmployeeStoreError("employee workflow command could not be stored") from error
