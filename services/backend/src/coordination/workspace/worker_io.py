"""Short fenced transactions and object-bound Storage capabilities for ALTO jobs."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from coordination.config import Settings
from coordination.db.session import company_transaction
from coordination.durable.contracts import JobLease
from coordination.durable.runner import PermanentJobError, RetryableJobError


@contextmanager
def job_transaction(settings: Settings, lease: JobLease, purpose: str) -> Iterator[Any]:
    if settings.database_url is None:
        raise PermanentJobError("database_not_configured")
    context = lease.company_context()
    with company_transaction(
        settings.database_url.get_secret_value(),
        role="coordination_worker",
        actor_id=context.actor.user_id,
        company_id=context.company_id,
        purpose=purpose,
        demo_run_id=context.demo_run_id,
        demo_actor_session_id=context.demo_actor_session_id,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    ) as connection:
        connection.execute(
            "select set_config('app.job_id',%s,true),set_config('app.lease_token',%s,true)",
            (str(lease.job_id), str(lease.lease_token)),
        )
        connection.execute(
            "select app.assert_alto_job_lease(%s,%s,%s)",
            (lease.company_id, lease.job_id, lease.lease_token),
        )
        yield connection


class WorkerStorage:
    def __init__(self, settings: Settings, lease: JobLease, file_id: UUID) -> None:
        if settings.supabase_url is None:
            raise PermanentJobError("storage_not_configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.lease = lease
        self.file_id = file_id

    def ticket(self, action: str) -> dict[str, Any]:
        try:
            response = httpx.post(
                self.base_url + "/functions/v1/worker-storage",
                json={
                    "companyId": str(self.lease.company_id),
                    "jobId": str(self.lease.job_id),
                    "leaseToken": str(self.lease.lease_token),
                    "fileId": str(self.file_id),
                    "action": action,
                },
                timeout=20,
                follow_redirects=False,
            )
            if response.status_code in {401, 403, 404}:
                raise PermanentJobError("storage_lease_unavailable")
            response.raise_for_status()
            ticket = response.json()
            if not isinstance(ticket, dict):
                raise ValueError("invalid storage ticket")
            if action != "delete-audio":
                target = urlsplit(ticket["signed_url"])
                origin = urlsplit(self.base_url)
                if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
                    raise PermanentJobError("storage_origin_mismatch")
            return dict(ticket)
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise RetryableJobError("storage_unavailable") from error

    def download(self, action: str, limit: int) -> tuple[bytes, dict[str, Any]]:
        ticket = self.ticket(action)
        try:
            data = bytearray()
            with httpx.stream(
                "GET", ticket["signed_url"], timeout=30, follow_redirects=False
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > limit:
                        raise PermanentJobError("file_too_large")
                    data.extend(chunk)
            if len(data) != ticket["size_bytes"]:
                raise PermanentJobError("file_size_mismatch")
            return bytes(data), ticket
        except httpx.HTTPError as error:
            raise RetryableJobError("storage_download_unavailable") from error

    def upload_private(self, data: bytes, content_type: str) -> str:
        ticket = self.ticket("upload-private")
        try:
            response = httpx.put(
                ticket["signed_url"],
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "false"},
                timeout=30,
            )
            if response.status_code in {400, 409}:
                existing, _ = self.download("download-private", len(data))
                if hashlib.sha256(existing).digest() == hashlib.sha256(data).digest():
                    return str(ticket["object_path"])
                raise PermanentJobError("storage_promotion_content_conflict")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise RetryableJobError("storage_promotion_unavailable") from error
        return str(ticket["object_path"])
