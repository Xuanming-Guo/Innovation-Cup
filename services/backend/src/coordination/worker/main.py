from __future__ import annotations

import argparse
import json
import signal
import socket
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict
from uuid import uuid4

from coordination.config import Settings, get_settings
from coordination.durable.contracts import WorkerIdentity
from coordination.durable.handlers import build_handlers
from coordination.durable.persistence import DurableStoreError, PostgresDurableStore
from coordination.durable.runner import DurableWorker
from coordination.workspace.cleanup import cleanup_expired_audio


def worker_status(settings: Settings, *, durable_schema_ready: bool = False) -> dict[str, object]:
    configuration_ready = settings.worker_configuration_valid
    return {
        "service": "coordination-worker",
        "status": "ready" if configuration_ready and durable_schema_ready else "not_ready",
        "build_commit": settings.build_commit,
        "environment": settings.environment,
        "checks": {
            "configuration": configuration_ready,
            "durable_schema": durable_schema_ready,
        },
        "queue_consumer_enabled": configuration_ready and durable_schema_ready,
        "gemini_credential_mode": "tenant_byok_api_key_or_vertex_service_account",
        "gemini_local_fallback_configured": (
            settings.environment != "production" and settings.gemini_api_key is not None
        ),
        "file_scanner_configured": settings.file_scanner_host is not None,
        "job_kinds": [
            "interpretation.run",
            "planning.materialize",
            "planning.run",
            "private_file.scan",
            "outbox.deliver",
            "plan.propose",
            "assistant.respond",
            "preference.suggest",
            "voice.transcribe",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordination Engine durable worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Lease and process at most one configured batch, then exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report non-secret worker configuration and exit without polling",
    )
    return parser


def emit_json(event: dict[str, object]) -> None:
    print(json.dumps(event, sort_keys=True, separators=(",", ":")), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if not settings.worker_configuration_valid or settings.database_url is None:
        emit_json(worker_status(settings))
        if args.status:
            return 2
        emit_json({"event": "worker.configuration_invalid"})
        return 2

    worker_identity = WorkerIdentity(
        worker_id=uuid4(),
        instance_name=settings.worker_instance_name or socket.gethostname(),
        build_commit=settings.build_commit,
        environment=settings.environment,
    )
    store = PostgresDurableStore(
        settings.database_url.get_secret_value(),
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        durable_schema_ready = store.ready()
    except DurableStoreError:
        durable_schema_ready = False
    emit_json(worker_status(settings, durable_schema_ready=durable_schema_ready))
    if not durable_schema_ready:
        if not args.status:
            emit_json({"event": "worker.durable_schema_unavailable"})
        return 3
    if args.status:
        return 0
    runner = DurableWorker(
        store=store,
        worker=worker_identity,
        handlers=build_handlers(settings, store),
        batch_size=settings.worker_batch_size,
        lease_seconds=settings.worker_lease_seconds,
        renewal_seconds=settings.worker_renewal_seconds,
        emit=emit_json,
    )
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    for signal_name in ("SIGTERM", "SIGINT"):
        candidate = getattr(signal, signal_name, None)
        if candidate is not None:
            signal.signal(candidate, request_stop)

    next_audio_cleanup = 0.0
    store_failures = 0
    while not stop.is_set():
        try:
            cycle = runner.run_once()
        except DurableStoreError:
            # A transient resolver/database outage must not terminate the worker
            # process. No lease is assumed while the store is unavailable; the
            # durable queue will make unfinished work eligible again after its
            # recorded lease expires.
            store_failures += 1
            retry_seconds = min(30.0, 2.0 ** min(store_failures - 1, 5))
            emit_json(
                {
                    "event": "worker.store_unavailable",
                    "retry_seconds": retry_seconds,
                }
            )
            if args.once:
                return 3
            stop.wait(retry_seconds)
            continue
        store_failures = 0
        if time.monotonic() >= next_audio_cleanup:
            removed = cleanup_expired_audio(settings, worker_identity.worker_id)
            next_audio_cleanup = time.monotonic() + 60
            if removed:
                emit_json({"event": "worker.expired_audio_removed", "count": removed})
        cycle_values = asdict(cycle)
        if args.once or any(cycle_values.values()):
            emit_json({"event": "worker.cycle", **cycle_values})
        if args.once:
            return 0
        stop.wait(settings.worker_poll_seconds)
    emit_json({"event": "worker.stopped"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
