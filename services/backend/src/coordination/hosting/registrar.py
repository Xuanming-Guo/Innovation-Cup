from __future__ import annotations

import argparse
import json
import re
import signal
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import psycopg
from psycopg.sql import SQL, Identifier

from coordination.config import get_settings

QUICK_TUNNEL_PATTERN = re.compile(
    r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com",
    re.IGNORECASE,
)


class HostLeaseConflictError(RuntimeError):
    """Another host currently owns the live company lease."""


class HostRegistry(Protocol):
    def heartbeat(self, api_origin: str) -> None: ...

    def release(self) -> bool: ...


def normalise_quick_tunnel_origin(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.trycloudflare\.com",
            hostname,
        )
    ):
        raise ValueError("tunnel URL is not one canonical Cloudflare Quick Tunnel origin")
    return f"https://{hostname}"


def extract_latest_quick_tunnel_origin(log_text: str) -> str | None:
    matches = QUICK_TUNNEL_PATTERN.findall(log_text)
    if not matches:
        return None
    return normalise_quick_tunnel_origin(matches[-1])


def read_latest_quick_tunnel_origin(path: Path) -> str | None:
    try:
        contents = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return None
    return extract_latest_quick_tunnel_origin(contents)


def public_api_is_ready(api_origin: str, *, timeout_seconds: float) -> bool:
    request = urllib.request.Request(
        f"{api_origin}/health/ready",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("service") == "coordination-api"
        and payload.get("status") == "ready"
    )


class PostgresHostRegistry:
    def __init__(
        self,
        *,
        dsn: str,
        company_id: UUID,
        actor_id: UUID,
        instance_id: UUID,
        build_commit: str,
        ttl_seconds: int,
        connect_timeout_seconds: int,
    ) -> None:
        self._dsn = dsn
        self._company_id = company_id
        self._actor_id = actor_id
        self._instance_id = instance_id
        self._build_commit = build_commit
        self._ttl_seconds = ttl_seconds
        self._connect_timeout_seconds = connect_timeout_seconds

    def heartbeat(self, api_origin: str) -> None:
        try:
            with (
                psycopg.connect(
                    self._dsn,
                    connect_timeout=self._connect_timeout_seconds,
                ) as connection,
                connection.transaction(),
            ):
                connection.execute(SQL("set local role {}").format(Identifier("coordination_api")))
                connection.execute(
                    "select set_config('app.actor_id', %s, true), "
                    "set_config('app.company_id', %s, true), "
                    "set_config('app.purpose', %s, true)",
                    (str(self._actor_id), str(self._company_id), "host:endpoint-heartbeat"),
                )
                connection.execute(
                    "select * from app.heartbeat_host_runtime_endpoint(%s, %s, %s, %s, %s)",
                    (
                        self._company_id,
                        self._instance_id,
                        api_origin,
                        self._build_commit,
                        self._ttl_seconds,
                    ),
                ).fetchone()
        except psycopg.errors.ObjectInUse as error:
            raise HostLeaseConflictError(
                "another host holds the active company lease"
            ) from error

    def release(self) -> bool:
        with (
            psycopg.connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
            ) as connection,
            connection.transaction(),
        ):
            connection.execute(SQL("set local role {}").format(Identifier("coordination_api")))
            connection.execute(
                "select set_config('app.actor_id', %s, true), "
                "set_config('app.company_id', %s, true), "
                "set_config('app.purpose', %s, true)",
                (str(self._actor_id), str(self._company_id), "host:endpoint-release"),
            )
            row = connection.execute(
                "select app.release_host_runtime_endpoint(%s, %s)",
                (self._company_id, self._instance_id),
            ).fetchone()
        return bool(row and row[0])


class HostRegistrar:
    def __init__(
        self,
        *,
        registry: HostRegistry,
        log_path: Path,
        ready_path: Path,
        heartbeat_seconds: float,
        health_timeout_seconds: float,
        health_check: Callable[..., bool] = public_api_is_ready,
    ) -> None:
        self._registry = registry
        self._log_path = log_path
        self._ready_path = ready_path
        self._heartbeat_seconds = heartbeat_seconds
        self._health_timeout_seconds = health_timeout_seconds
        self._health_check = health_check
        self._active_origin: str | None = None
        self._next_heartbeat_at = 0.0
        self._registered = False
        self._ready_path.unlink(missing_ok=True)

    def tick(self, *, now: float) -> str | None:
        origin = read_latest_quick_tunnel_origin(self._log_path)
        if origin is None:
            return None
        if origin == self._active_origin and now < self._next_heartbeat_at:
            return self._active_origin
        if not self._health_check(origin, timeout_seconds=self._health_timeout_seconds):
            return None
        self._registry.heartbeat(origin)
        self._active_origin = origin
        self._next_heartbeat_at = now + self._heartbeat_seconds
        self._registered = True
        self._ready_path.write_text(origin, encoding="utf-8")
        return origin

    def close(self) -> None:
        try:
            if self._registered:
                self._registry.release()
        finally:
            self._ready_path.unlink(missing_ok=True)


def ready_probe(path: Path, *, ttl_seconds: int) -> bool:
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds <= ttl_seconds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordination Engine laptop-host registrar")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Exit successfully only while the host lease heartbeat marker is fresh",
    )
    return parser


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, separators=(",", ":")), flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    if args.probe:
        is_ready = ready_probe(
            settings.host_ready_path,
            ttl_seconds=settings.host_ttl_seconds,
        )
        return 0 if is_ready else 1
    if (
        not settings.host_registrar_configuration_valid
        or settings.database_url is None
        or settings.host_company_id is None
        or settings.host_actor_id is None
        or settings.host_instance_id is None
    ):
        emit("host.configuration_invalid")
        return 2

    registry = PostgresHostRegistry(
        dsn=settings.database_url.get_secret_value(),
        company_id=settings.host_company_id,
        actor_id=settings.host_actor_id,
        instance_id=settings.host_instance_id,
        build_commit=settings.build_commit,
        ttl_seconds=settings.host_ttl_seconds,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    registrar = HostRegistrar(
        registry=registry,
        log_path=settings.host_tunnel_log_path,
        ready_path=settings.host_ready_path,
        heartbeat_seconds=settings.host_heartbeat_seconds,
        health_timeout_seconds=settings.host_health_timeout_seconds,
    )
    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    for signal_name in ("SIGTERM", "SIGINT"):
        candidate = getattr(signal, signal_name, None)
        if candidate is not None:
            signal.signal(candidate, request_stop)

    announced_origin: str | None = None
    try:
        while not stop.is_set():
            try:
                origin = registrar.tick(now=time.monotonic())
                if origin is not None and origin != announced_origin:
                    emit("host.online", api_origin=origin)
                    announced_origin = origin
            except HostLeaseConflictError:
                emit("host.lease_conflict")
                return 4
            except (OSError, psycopg.Error):
                emit("host.registration_retry")
            stop.wait(settings.host_poll_seconds)
    finally:
        try:
            registrar.close()
        except (OSError, psycopg.Error):
            emit("host.release_failed")
    emit("host.stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
