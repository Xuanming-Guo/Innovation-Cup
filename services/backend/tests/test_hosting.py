from pathlib import Path

import pytest

from coordination.hosting.registrar import (
    HostRegistrar,
    extract_latest_quick_tunnel_origin,
    normalise_quick_tunnel_origin,
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
            'first URL https://old-host.trycloudflare.com',
            'replacement URL https://new-host.trycloudflare.com',
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
