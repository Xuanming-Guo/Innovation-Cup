"""Explicit employee commands; no assistant output is itself authorisation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from coordination.auth.models import CompanyContext
from coordination.workspace.contracts import FeedbackRequest, VoiceRequest
from coordination.workspace.persistence import (
    PostgresWorkspaceStore,
    WorkspaceConflictError,
    WorkspaceNotFoundError,
)


def file_status(
    store: PostgresWorkspaceStore, context: CompanyContext, file_id: UUID
) -> dict[str, Any]:
    with store.transaction(context, "file:status") as connection:
        row = connection.execute(
            """select id,state,scan_state from app.private_files where company_id=%s and id=%s
          and uploader_employee_id=%s and deleted_at is null""",
            (context.company_id, file_id, context.effective_employee_id),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFoundError("file was not found")
        return dict(row)


def finalize_upload(
    store: PostgresWorkspaceStore, context: CompanyContext, file_id: UUID, size: int, key: str
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            "select app.finalize_alto_upload(%s,%s,%s) as finalized",
            (context.company_id, file_id, size),
        ).fetchone()
        if not row["finalized"]:
            raise WorkspaceConflictError("upload is no longer pending or its declared size changed")
        return {"id": str(file_id)}

    store.command(
        context,
        name=f"file-finalize:{file_id}",
        key=key,
        body={"size_bytes": size},
        operation=write,
    )
    return file_status(store, context, file_id)


def enqueue(
    connection: Any,
    context: CompanyContext,
    kind: str,
    aggregate: UUID,
    payload: dict[str, str],
    key: str,
) -> UUID:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).digest()
    row = connection.execute(
        "select app.enqueue_alto_job(%s,%s,%s,%s,%s,%s,%s) as id",
        (context.company_id, kind, aggregate, Jsonb(payload), key, digest, uuid4()),
    ).fetchone()
    return UUID(str(row["id"]))


def start_transcription(
    store: PostgresWorkspaceStore, context: CompanyContext, body: VoiceRequest, key: str
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        row = connection.execute(
            """select id from app.private_files where company_id=%s and id=%s and thread_id=%s
          and purpose='voice_audio' and state='available' and scan_state='clean' and deleted_at
          is null
          and expires_at>statement_timestamp() and uploader_employee_id=%s""",
            (context.company_id, body.file_id, body.thread_id, context.effective_employee_id),
        ).fetchone()
        if row is None:
            raise WorkspaceConflictError(
                "audio is not yet validated; wait for scanning or record again"
            )
        job = enqueue(
            connection,
            context,
            "voice.transcribe",
            body.file_id,
            {"file_id": str(body.file_id), "thread_id": str(body.thread_id)},
            key,
        )
        return {"id": str(job)}

    result = store.command(
        context, name="voice-transcribe", key=key, body=body.model_dump(), operation=write
    )
    return transcription(store, context, UUID(result["id"]))


def transcription(
    store: PostgresWorkspaceStore, context: CompanyContext, job_id: UUID
) -> dict[str, Any]:
    with store.transaction(context, "voice:result") as connection:
        job = connection.execute(
            """select j.state,j.last_error_code from app.durable_jobs j
          join app.private_files f on f.company_id=j.company_id and f.id=j.aggregate_id
          where j.company_id=%s and j.id=%s and j.job_kind='voice.transcribe'
          and f.uploader_employee_id=%s and app.owns_thread(f.company_id,f.thread_id)""",
            (context.company_id, job_id, context.effective_employee_id),
        ).fetchone()
        if job is None:
            raise WorkspaceNotFoundError("transcription was not found")
        result = connection.execute(
            "select transcript from app.voice_transcriptions where company_id=%s and id=%s",
            (context.company_id, job_id),
        ).fetchone()
        status = {
            "leased": "running",
            "retry_scheduled": "queued",
            "succeeded": "completed",
            "dead_letter": "failed",
            "review_required": "failed",
        }.get(job["state"], job["state"])
        if result:
            status = "completed"
        return {
            "id": str(job_id),
            "status": status,
            "transcript": result["transcript"] if result else None,
            "error": job["last_error_code"] if status == "failed" else None,
        }


def record_feedback(
    store: PostgresWorkspaceStore, context: CompanyContext, body: FeedbackRequest, key: str
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        if body.task_id:
            task = connection.execute(
                """select w.task_id from app.work_items w join app.execution_resources r
              on r.company_id=w.company_id and r.id=w.owner_resource_id
              where w.company_id=%s and w.task_id=%s and r.employee_id=%s and
              w.status='accepted'""",
                (context.company_id, body.task_id, context.effective_employee_id),
            ).fetchone()
            if task is None:
                raise WorkspaceConflictError("work feedback requires your accepted task version")
        row = connection.execute(
            (
                "insert into "
                "app.employee_feedback_entries(company_id,demo_run_id,employee_id,task_id,body) "
                "values(%s,%s,%s,%s,%s) returning id"
            ),
            (
                context.company_id,
                context.demo_run_id,
                context.effective_employee_id,
                body.task_id,
                body.text,
            ),
        ).fetchone()
        job_id = (
            enqueue(
                connection,
                context,
                "preference.suggest",
                row["id"],
                {"feedback_id": str(row["id"])},
                key,
            )
            if body.suggest_preference
            else None
        )
        return {"id": str(row["id"]), "operation_id": str(job_id) if job_id else None}

    return store.command(
        context, name="private-feedback", key=key, body=body.model_dump(), operation=write
    )


def create_preference(
    store: PostgresWorkspaceStore, context: CompanyContext, text: str, key: str
) -> dict[str, Any]:
    def write(connection: Any) -> dict[str, Any]:
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))",
            (f"preference:{context.demo_run_id}:{context.effective_employee_id}",),
        )
        row = connection.execute(
            """insert into
            app.employee_preference_versions(company_id,demo_run_id,employee_id,version,text,origin,status)
          select %s,%s,%s,coalesce(max(version),0)+1,%s,'employee','confirmed'
          from app.employee_preference_versions where company_id=%s and employee_id=%s returning
          id""",
            (
                context.company_id,
                context.demo_run_id,
                context.effective_employee_id,
                text,
                context.company_id,
                context.effective_employee_id,
            ),
        ).fetchone()
        return {"id": str(row["id"])}

    return store.command(
        context, name="employee-preference", key=key, body={"text": text}, operation=write
    )
