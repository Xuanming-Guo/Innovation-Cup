"""Actual byte validation plus ClamAV, followed by fenced private publication."""

from __future__ import annotations

import hashlib
import io
import json
import socket
import struct
import subprocess
import zipfile
from typing import Any
from uuid import UUID

from coordination.config import Settings
from coordination.durable.contracts import JobLease, JobResult
from coordination.durable.runner import RetryableJobError
from coordination.workspace.worker_io import WorkerStorage, job_transaction


def validate_file(data: bytes, mime: str, settings: Settings) -> dict[str, Any]:
    if not data or len(data) > 26_214_400:
        raise ValueError("size")
    if mime == "application/pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-4096:]:
            raise ValueError("pdf_structure")
    elif mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 2000 or sum(item.file_size for item in entries) > 80_000_000:
                raise ValueError("archive_expansion")
            names = {item.filename for item in entries}
            if not {"[Content_Types].xml", "word/document.xml"} <= names:
                raise ValueError("docx_structure")
            if any(
                item.flag_bits & 1
                or ".." in item.filename.split("/")
                or item.filename.startswith("/")
                or item.filename.lower().endswith((".exe", ".js", ".vbs", "vbaproject.bin"))
                for item in entries
            ):
                raise ValueError("docx_active_content")
    elif mime in {"text/plain", "text/csv"}:
        text = data.decode("utf-8-sig")
        if "\0" in text:
            raise ValueError("binary_text")
    elif mime in {"image/png", "image/jpeg", "audio/webm", "audio/mp4", "audio/wav"}:
        if len(data) > (8_388_608 if mime.startswith("audio/") else 10_485_760):
            raise ValueError("media_size")
        if mime == "image/png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("png_header")
        if mime == "image/jpeg" and not data.startswith(b"\xff\xd8\xff"):
            raise ValueError("jpeg_header")
        signatures = {
            "audio/webm": data.startswith(b"\x1a\x45\xdf\xa3"),
            "audio/mp4": data[4:8] == b"ftyp",
            "audio/wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
        }
        if mime in signatures and not signatures[mime]:
            raise ValueError("audio_header")
        result = subprocess.run(
            [
                settings.ffprobe_binary,
                "-v",
                "error",
                "-protocol_whitelist",
                "pipe",
                "-show_streams",
                "-show_format",
                "-show_packets",
                "-of",
                "json",
                "pipe:0",
            ],
            input=data,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError("media_decode")
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        if mime.startswith("audio/"):
            if not streams or any(s.get("codec_type") != "audio" for s in streams):
                raise ValueError("audio_tracks")
            durations = [
                float(s["duration"]) for s in streams if s.get("duration") not in (None, "N/A")
            ]
            packets = metadata.get("packets", [])
            # Stopped MediaRecorder WebM commonly has no duration header. Measure
            # the demuxed final packet timestamp; never trust a browser duration.
            timed = [p for p in packets if p.get("pts_time") not in (None, "N/A")]
            if timed:
                durations.append(
                    max(float(p["pts_time"]) + float(p.get("duration_time", 0)) for p in timed)
                    - min(float(p["pts_time"]) for p in timed)
                )
            declared_duration = metadata.get("format", {}).get("duration")
            duration = (
                float(declared_duration)
                if declared_duration not in (None, "", "N/A")
                else max(durations, default=0)
            )
            if not 0 < duration <= 60:
                raise ValueError("audio_duration")
            return {"audio_duration_seconds": duration}
        if not streams or any(
            int(s.get("width", 0)) * int(s.get("height", 0)) > 40_000_000 for s in streams
        ):
            raise ValueError("image_dimensions")
    else:
        raise ValueError("mime_not_allowed")
    return {}


def clam_scan(data: bytes, settings: Settings) -> tuple[str, str]:
    if not settings.file_scanner_host:
        raise RetryableJobError("file_scanner_not_configured")

    def read_reply(client: socket.socket) -> str:
        result = bytearray()
        while b"\0" not in result:
            chunk = client.recv(4096)
            if not chunk or len(result) + len(chunk) > 8192:
                break
            result.extend(chunk)
        return result.rstrip(b"\0").decode("utf-8", errors="replace")

    try:
        address = (settings.file_scanner_host, settings.file_scanner_port)
        with socket.create_connection(
            address, timeout=settings.file_scanner_timeout_seconds
        ) as client:
            client.sendall(b"zVERSION\0")
            version = read_reply(client)
        if not version.startswith("ClamAV "):
            raise RetryableJobError("file_scanner_invalid_version")
        with socket.create_connection(
            address, timeout=settings.file_scanner_timeout_seconds
        ) as client:
            client.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 65_536):
                chunk = data[offset : offset + 65_536]
                client.sendall(struct.pack("!I", len(chunk)) + chunk)
            client.sendall(struct.pack("!I", 0))
            verdict = read_reply(client)
        if verdict.endswith(" FOUND"):
            return "rejected", version[:120]
        if verdict != "stream: OK":
            raise RetryableJobError("file_scanner_incomplete")
        return "clean", version[:120]
    except OSError as error:
        raise RetryableJobError("file_scanner_unavailable") from error


class FileScanJobHandler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def __call__(self, lease: JobLease) -> JobResult:
        file_id = UUID(str(lease.payload["file_id"]))
        with job_transaction(self.settings, lease, "file:reconcile") as connection:
            existing = connection.execute(
                "select state from app.private_files where company_id=%s and id=%s",
                (lease.company_id, file_id),
            ).fetchone()
            if existing and existing["state"] in {"available", "rejected"}:
                return JobResult(
                    values={"file_id": str(file_id), "state": existing["state"], "reconciled": True}
                )
        storage = WorkerStorage(self.settings, lease, file_id)
        data, ticket = storage.download("download-quarantine", 26_214_400)
        mime = str(ticket["content_type"])
        verdict, engine = clam_scan(data, self.settings)
        metadata: dict[str, Any] = {}
        if verdict == "clean":
            try:
                metadata = validate_file(data, mime, self.settings)
            except (ValueError, zipfile.BadZipFile, UnicodeError):
                verdict = "rejected"
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RetryableJobError("file_validator_unavailable") from error
        with job_transaction(self.settings, lease, "file:pre-promotion"):
            pass
        path = storage.upload_private(data, mime) if verdict == "clean" else None
        with job_transaction(self.settings, lease, "file:scan-result") as connection:
            job = connection.execute(
                "select app.current_alto_lease_worker() as lease_owner"
            ).fetchone()
            state = connection.execute(
                (
                    "select "
                    "app.record_leased_private_file_scan(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) as "
                    "state"
                ),
                (
                    lease.company_id,
                    lease.job_id,
                    job["lease_owner"],
                    lease.lease_token,
                    file_id,
                    verdict,
                    mime,
                    len(data),
                    hashlib.sha256(data).digest(),
                    engine,
                    path,
                ),
            ).fetchone()["state"]
            if metadata.get("audio_duration_seconds"):
                connection.execute(
                    (
                        "update app.private_files set audio_duration_seconds=%s where "
                        "company_id=%s and id=%s"
                    ),
                    (metadata["audio_duration_seconds"], lease.company_id, file_id),
                )
        return JobResult(values={"file_id": str(file_id), "state": state})
