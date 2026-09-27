from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.genai import types

from coordination.ai_rate_limit import (
    DemoAiCommandLimiter,
    DemoAiCommandRateLimitError,
    GeminiRequestLimiter,
    admit_demo_ai_command,
)
from coordination.api.main import create_app
from coordination.auth.models import AuthenticatedUser, CompanyContext
from coordination.config import Settings
from coordination.durable.handlers import build_handlers
from coordination.interpretation.gateway import GatewayConfiguration, GoogleGeminiGateway
from coordination.workspace import interactions
from coordination.workspace.routes import get_workspace_store, workspace_context


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def anonymous_context() -> CompanyContext:
    return CompanyContext(
        actor=AuthenticatedUser(uuid4(), "authenticated", uuid4(), "aal1", is_anonymous=True),
        company_id=uuid4(),
        membership_id=uuid4(),
        administrative_role="manager",
        employee_id=None,
        demo_run_id=uuid4(),
        demo_actor_session_id=uuid4(),
        demo_planning_authority=True,
    )


def settings(**values: Any) -> Settings:
    return Settings(**{"_env_file": None, "environment": "test", **values})


def test_command_window_counts_unique_keys_per_judge_and_prunes_expired_entries() -> None:
    clock = FakeClock()
    limiter = DemoAiCommandLimiter(12, clock=clock)
    first = anonymous_context()
    second = anonymous_context()

    for index in range(12):
        limiter.admit(str(first.actor.user_id), f"command-{index}")
    limiter.admit(str(first.actor.user_id), "command-0")
    limiter.admit(str(second.actor.user_id), "independent-command")

    with pytest.raises(DemoAiCommandRateLimitError) as caught:
        limiter.admit(str(first.actor.user_id), "command-12")
    assert caught.value.retry_after_seconds == 60

    clock.now += 60
    limiter.admit(str(first.actor.user_id), "command-12")
    assert set(limiter._events) == {str(first.actor.user_id)}


def test_command_limit_returns_safe_429_with_retry_after_only_for_locked_demo_actor() -> None:
    context = anonymous_context()
    limiter = DemoAiCommandLimiter(1)
    admit_demo_ai_command(limiter, context, "accepted-command")
    admit_demo_ai_command(limiter, context, "accepted-command")

    with pytest.raises(HTTPException) as caught:
        admit_demo_ai_command(limiter, context, "rejected-command")
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "60"}
    assert caught.value.detail == (
        "This demo has received too many new AI requests. Retry in 60 seconds."
    )

    ordinary = CompanyContext(
        actor=context.actor,
        company_id=context.company_id,
        membership_id=context.membership_id,
        administrative_role="manager",
        employee_id=None,
    )
    admit_demo_ai_command(limiter, ordinary, "ordinary-installation")


def test_assistant_endpoint_admits_twelve_unique_commands_and_rejects_the_thirteenth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = anonymous_context()
    thread_id = uuid4()
    application = create_app()
    application.state.demo_ai_command_limiter = DemoAiCommandLimiter(12)
    application.dependency_overrides[workspace_context] = lambda: context
    application.dependency_overrides[get_workspace_store] = lambda: SimpleNamespace()
    monkeypatch.setattr(
        interactions,
        "send_message",
        lambda *_args, **_kwargs: {"id": str(thread_id), "status": "queued"},
    )
    body = {"content": "Hello", "context": {"kind": "global"}}

    with TestClient(application) as client:
        for index in range(12):
            response = client.post(
                f"/v1/companies/{context.company_id}/assistant/threads/{thread_id}/messages",
                headers={"Idempotency-Key": f"assistant-command-{index:02}"},
                json=body,
            )
            assert response.status_code == 200

        replay = client.post(
            f"/v1/companies/{context.company_id}/assistant/threads/{thread_id}/messages",
            headers={"Idempotency-Key": "assistant-command-00"},
            json=body,
        )
        rejected = client.post(
            f"/v1/companies/{context.company_id}/assistant/threads/{thread_id}/messages",
            headers={"Idempotency-Key": "assistant-command-12"},
            json=body,
        )

    assert replay.status_code == 200
    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"] == "60"


def test_provider_window_waits_then_reserves_without_failing_the_call() -> None:
    clock = FakeClock()
    limiter = GeminiRequestLimiter(120, clock=clock, sleeper=clock.sleep)
    for _ in range(120):
        limiter.acquire()

    limiter.acquire()

    assert clock.sleeps == [60.0]


def test_provider_reservations_are_thread_safe() -> None:
    limiter = GeminiRequestLimiter(200)
    with ThreadPoolExecutor(max_workers=16) as executor:
        completed = list(executor.map(lambda _: limiter.acquire(), range(200)))
    assert completed == [None] * 200
    assert len(limiter._events) == 200


def test_google_gateway_reserves_immediately_before_the_sdk_call() -> None:
    events: list[str] = []

    class RecordingLimiter:
        def acquire(self) -> None:
            events.append("reserved")

    class Models:
        def generate_content(self, **_: Any) -> object:
            events.append("sdk")
            return object()

    client = SimpleNamespace(models=Models())
    gateway = GoogleGeminiGateway(
        configuration=GatewayConfiguration(model="gemini-test"),
        request_limiter=RecordingLimiter(),  # type: ignore[arg-type]
        client=client,
    )

    gateway._request_content(
        system_instruction="system",
        prompt="prompt",
        response_schema=types.Schema(type=types.Type.OBJECT, properties={}),
    )

    assert events == ["reserved", "sdk"]


def test_worker_build_shares_one_provider_window_across_every_ai_handler() -> None:
    configured = settings(
        database_url="postgresql://unused",
        hackathon_demo=True,
        demo_ai_model_calls_per_minute=120,
    )
    handlers = build_handlers(configured, SimpleNamespace())

    interpretation = handlers["interpretation.run"]
    shared = interpretation._request_limiter  # type: ignore[attr-defined]
    assert isinstance(shared, GeminiRequestLimiter)
    assert interpretation._gateway_factory._request_limiter is shared  # type: ignore[attr-defined]
    assert handlers["plan.propose"]._request_limiter is shared  # type: ignore[attr-defined]
    for kind in ("assistant.respond", "preference.suggest", "voice.transcribe"):
        handler = handlers[kind]
        assert handler.request_limiter is shared  # type: ignore[attr-defined]
        assert handler.factory._request_limiter is shared  # type: ignore[attr-defined]


def test_worker_build_disables_provider_window_outside_hackathon_mode() -> None:
    configured = settings(
        database_url="postgresql://unused",
        hackathon_demo=False,
    )
    handlers = build_handlers(configured, SimpleNamespace())
    assert handlers["interpretation.run"]._request_limiter is None  # type: ignore[attr-defined]
    assert handlers["plan.propose"]._request_limiter is None  # type: ignore[attr-defined]
    assert handlers["assistant.respond"].request_limiter is None  # type: ignore[attr-defined]
