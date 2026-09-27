"""Recoverable expiry deletion, including abandoned audio in archived demo runs."""

from __future__ import annotations

from uuid import UUID

import httpx
import psycopg

from coordination.config import Settings
from coordination.db.session import worker_transaction


def cleanup_expired_audio(settings: Settings, worker_id: UUID) -> int:
    if settings.database_url is None or settings.supabase_url is None:
        return 0
    try:
        with worker_transaction(
            settings.database_url.get_secret_value(),
            purpose="voice:expiry-cleanup",
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
        ) as connection:
            records = connection.execute(
                "select * from app.claim_expired_audio_cleanup(%s,%s)", (worker_id, 2)
            ).fetchall()
        deleted = 0
        for record in records:
            try:
                response = httpx.post(
                    settings.supabase_url.rstrip("/") + "/functions/v1/worker-storage",
                    json={
                        "action": "cleanup-expired-audio",
                        "fileId": str(record["file_id"]),
                        "cleanupToken": str(record["cleanup_token"]),
                    },
                    timeout=20,
                    follow_redirects=False,
                )
                if response.status_code == 200:
                    deleted += 1
            except httpx.HTTPError:
                # The deletion lease expires and can be claimed again. Do not log tokens.
                continue
        return deleted
    except psycopg.Error:
        return 0
