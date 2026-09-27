import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import psycopg
import pytest

from coordination.hosting import registrar as registrar_module
from coordination.hosting.registrar import (
    HostRegistrar,
    extract_latest_quick_tunnel_origin,
    normalise_quick_tunnel_origin,
    public_api_readiness,
    ready_origin,
    ready_probe,
)


class FakeRegistry:
    def __init__(self) -> None:
        self.heartbeats: list[str] = []
        self.releases = 0

    def heartbeat(self, api_origin: str) -> None:
        self.heartbeats.append(api_origin)

    def release(self) -> bool:
        self.releases += 1
        return True


def test_quick_tunnel_origin_is_narrow_and_canonical() -> None:
    assert (
        normalise_quick_tunnel_origin("HTTPS://Demo-Host.trycloudflare.com/")
        == "https://demo-host.trycloudflare.com"
    )
    for value in (
        "http://demo-host.trycloudflare.com",
        "https://demo-host.trycloudflare.com/path",
        "https://demo-host.trycloudflare.com?token=value",
        "https://user@demo-host.trycloudflare.com",
        "https://api.example.com",
    ):
        with pytest.raises(ValueError):
            normalise_quick_tunnel_origin(value)


def test_latest_tunnel_origin_wins_when_cloudflared_restarts() -> None:
    logs = "\n".join(
        (
            "first URL https://old-host.trycloudflare.com",
            "replacement URL https://new-host.trycloudflare.com",
        )
    )

    assert extract_latest_quick_tunnel_origin(logs) == "https://new-host.trycloudflare.com"


def test_registrar_publishes_only_after_public_readiness_and_releases(tmp_path: Path) -> None:
    log_path = tmp_path / "cloudflared.log"
    ready_path = tmp_path / "ready"
    log_path.write_text("https://team-host.trycloudflare.com", encoding="utf-8")
    registry = FakeRegistry()
    attempts = iter((False, True))
    registrar = HostRegistrar(
        registry=registry,
        log_path=log_path,
        ready_path=ready_path,
        heartbeat_seconds=30,
        health_timeout_seconds=1,
        health_check=lambda _origin, **_kwargs: next(attempts),
    )

    assert registrar.tick(now=0) is None
    assert registry.heartbeats == []
    assert registrar.tick(now=1) == "https://team-host.trycloudflare.com"
    assert registry.heartbeats == ["https://team-host.trycloudflare.com"]
    assert ready_path.read_text(encoding="utf-8") == "https://team-host.trycloudflare.com"
    assert registrar.tick(now=10) == "https://team-host.trycloudflare.com"
    assert len(registry.heartbeats) == 1

    registrar.close()

    assert registry.releases == 1
    assert not ready_path.exists()


def test_ready_probe_rejects_a_missing_marker(tmp_path: Path) -> None:
    assert not ready_probe(tmp_path / "missing", ttl_seconds=120)


@pytest.mark.parametrize(
    "error,expected",
    [
        (urllib.error.URLError(socket.gaierror(-2, "private details")), "public_dns_unresolved"),
        (urllib.error.URLError(ssl.SSLError("private details")), "public_tls_error"),
        (urllib.error.URLError(TimeoutError("private details")), "public_timeout"),
        (TimeoutError("private details"), "public_timeout"),
        (urllib.error.URLError(ConnectionError("private details")), "public_network_error"),
        (
            urllib.error.HTTPError("private URL", 502, "private details", Message(), None),
            "public_http_error",
        ),
    ],
)
def test_public_readiness_reports_only_safe_failure_categories(
    monkeypatch: pytest.MonkeyPatch, error: Exception, expected: str
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", Mock(side_effect=error))
    assert public_api_readiness("https://demo.trycloudflare.com", timeout_seconds=1) == expected


@pytest.mark.parametrize(
    "body,redirected,expected",
    [
        (b'{"service":"coordination-api","status":"ready"}', False, "ready"),
        (b'{"service":"coordination-api","status":"ready"}', True, "public_response_invalid"),
        (b'{"service":"other","status":"ready"}', False, "public_response_invalid"),
        (b"<html>private error page</html>", False, "public_response_invalid"),
    ],
)
def test_public_readiness_requires_exact_service_without_redirect(
    monkeypatch: pytest.MonkeyPatch, body: bytes, redirected: bool, expected: str
) -> None:
    response = Mock()
    response.status = 200
    response.geturl.return_value = (
        "https://elsewhere.example/"
        if redirected
        else "https://demo.trycloudflare.com/health/ready"
    )
    response.read.return_value = body
    manager = Mock()
    manager.__enter__ = Mock(return_value=response)
    manager.__exit__ = Mock(return_value=None)
    monkeypatch.setattr(urllib.request, "urlopen", Mock(return_value=manager))
    assert public_api_readiness("https://demo.trycloudflare.com", timeout_seconds=1) == expected
    if not redirected:
        response.read.assert_called_once_with(4097)


def test_failed_public_recheck_clears_marker_and_rotated_origin_must_pass(tmp_path: Path) -> None:
    log_path, ready_path = tmp_path / "tunnel.log", tmp_path / "ready"
    old, new = "https://old.trycloudflare.com", "https://new.trycloudflare.com"
    log_path.write_text(old, encoding="utf-8")
    registry = FakeRegistry()
    checks = iter(("ready", "public_dns_unresolved", "public_http_error", "ready"))
    registrar = HostRegistrar(
        registry=registry,
        log_path=log_path,
        ready_path=ready_path,
        heartbeat_seconds=30,
        health_timeout_seconds=1,
        health_check=lambda *_args, **_kwargs: next(checks),
    )
    assert registrar.tick(now=0) == old and ready_probe(ready_path, ttl_seconds=120)
    assert registrar.tick(now=31) is None and not ready_path.exists()
    assert registrar.status == "public_dns_unresolved"
    log_path.write_text(f"{old}\n{new}", encoding="utf-8")
    assert registrar.tick(now=32) is None and registry.heartbeats == [old]
    assert registrar.tick(now=33) == new and registry.heartbeats == [old, new]
    assert ready_origin(ready_path, ttl_seconds=120) == new


def test_failed_database_heartbeat_clears_local_marker_without_rotating_tunnel(
    tmp_path: Path,
) -> None:
    log_path, ready_path = tmp_path / "tunnel.log", tmp_path / "ready"
    origin = "https://demo.trycloudflare.com"
    log_path.write_text(origin, encoding="utf-8")
    registry = Mock()
    registry.heartbeat.side_effect = [None, psycopg.OperationalError("private details")]
    registrar = HostRegistrar(
        registry=registry,
        log_path=log_path,
        ready_path=ready_path,
        heartbeat_seconds=30,
        health_timeout_seconds=1,
        health_check=lambda *_a, **_k: True,
    )
    assert registrar.tick(now=0) == origin
    with pytest.raises(psycopg.OperationalError):
        registrar.tick(now=31)
    assert not ready_path.exists() and registrar.status == "registration_pending"
    registry.release.assert_not_called()


@pytest.mark.parametrize("age", [-60, 121])
def test_ready_probe_rejects_future_or_expired_marker(tmp_path: Path, age: int) -> None:
    marker = tmp_path / "ready"
    marker.write_text("https://demo.trycloudflare.com", encoding="utf-8")
    stamp = time.time() - age
    os.utime(marker, (stamp, stamp))
    assert not ready_probe(marker, ttl_seconds=120)


@pytest.mark.parametrize("current", [False, True])
def test_status_reports_only_current_validated_registered_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: Any, current: bool
) -> None:
    marker, log_path = tmp_path / "ready", tmp_path / "tunnel.log"
    old, new = "https://old.trycloudflare.com", "https://new.trycloudflare.com"
    marker.write_text(new if current else old, encoding="utf-8")
    log_path.write_text(f"{old}\n{new}", encoding="utf-8")
    monkeypatch.setattr(
        registrar_module,
        "get_settings",
        lambda: SimpleNamespace(
            host_ready_path=marker,
            host_ttl_seconds=120,
            host_tunnel_log_path=log_path,
        ),
    )
    assert registrar_module.main(["--status"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ready": current,
        "api_origin": new if current else None,
    }
    assert registrar_module.main(["--probe"]) == (0 if current else 1)
