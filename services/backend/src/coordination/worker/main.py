from __future__ import annotations

import argparse
import json
import signal
import socket
import threading
from collections.abc import Sequence
from dataclasses import asdict
from uuid import uuid4

from coordination.config import Settings, get_settings
from coordination.durable.contracts import WorkerIdentity
from coordination.durable.handlers import build_handlers
from coordination.durable.persistence import DurableStoreError, PostgresDurableStore
from coordination.durable.runner import DurableWorker


def worker_status(
    settings: Settings, *, durable_schema_ready: bool = False
) -> dict[str, object]:
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
        "gemini_configured": settings.gemini_api_key is not None,
        "file_scanner_configured": False,
        "job_kinds": [
            "interpretation.run",
            "planning.run",
            "private_file.scan",
            "outbox.deliver",
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

    while not stop.is_set():
        cycle = runner.run_once()
        emit_json({"event": "worker.cycle", **asdict(cycle)})
        if args.once:
            return 0
        stop.wait(settings.worker_poll_seconds)
    emit_json({"event": "worker.stopped"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
