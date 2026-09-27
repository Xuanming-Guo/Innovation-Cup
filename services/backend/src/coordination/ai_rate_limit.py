"""Process-local limits for the locked, single-host hackathon demo.

The API limiter protects one anonymous judge from enqueueing an unbounded amount
of AI work. The provider limiter is shared by every Gemini gateway in the worker
and waits for capacity so an already accepted durable job is not failed merely
because the host is busy.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Annotated, TypeAlias, cast

from fastapi import Depends, HTTPException, Request, status

from coordination.auth.models import CompanyContext


@dataclass(frozen=True, slots=True)
class DemoAiCommandRateLimitError(Exception):
    retry_after_seconds: int


class DemoAiCommandLimiter:
    """Thread-safe rolling window keyed by anonymous Auth user and command key."""

    def __init__(
        self,
        limit: int | None,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit is not None and limit < 1:
            raise ValueError("command limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[tuple[float, str]]] = {}
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._limit is not None

    def admit(self, subject: str, idempotency_key: str) -> None:
        if self._limit is None:
            return
        now = self._clock()
        cutoff = now - self._window_seconds
        with self._lock:
            # Prune every subject on every check. This keeps the process-local
            # state bounded to commands in the current rolling window.
            for known_subject in tuple(self._events):
                entries = self._events[known_subject]
                while entries and entries[0][0] <= cutoff:
                    entries.popleft()
                if not entries:
                    del self._events[known_subject]

            entries = self._events.setdefault(subject, deque())
            if any(key == idempotency_key for _, key in entries):
                return
            assert self._limit is not None
            if len(entries) >= self._limit:
                retry_after = max(1, math.ceil(entries[0][0] + self._window_seconds - now))
                raise DemoAiCommandRateLimitError(retry_after)
            entries.append((now, idempotency_key))


class GeminiRequestLimiter:
    """Thread-safe blocking rolling window for actual Google SDK attempts."""

    def __init__(
        self,
        limit: int,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if limit < 1:
            raise ValueError("provider limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._events: deque[float] = deque()
        self._lock = Lock()

    def _capacity_wait(self, *, reserve: bool) -> float:
        now = self._clock()
        cutoff = now - self._window_seconds
        with self._lock:
            while self._events and self._events[0] <= cutoff:
                self._events.popleft()
            if len(self._events) < self._limit:
                if reserve:
                    self._events.append(now)
                return 0.0
            return max(0.001, self._events[0] + self._window_seconds - now)

    def wait_until_available(self) -> None:
        """Wait without reserving, for use before durable model-run evidence begins."""

        while (wait_seconds := self._capacity_wait(reserve=False)) > 0:
            self._sleeper(wait_seconds)

    def acquire(self) -> None:
        """Reserve one provider attempt immediately before the SDK request."""

        while (wait_seconds := self._capacity_wait(reserve=True)) > 0:
            self._sleeper(wait_seconds)


def get_demo_ai_command_limiter(request: Request) -> DemoAiCommandLimiter:
    return cast(DemoAiCommandLimiter, request.app.state.demo_ai_command_limiter)


DemoAiCommandLimiterDependency: TypeAlias = Annotated[
    DemoAiCommandLimiter, Depends(get_demo_ai_command_limiter)
]


def admit_demo_ai_command(
    limiter: DemoAiCommandLimiter,
    context: CompanyContext,
    idempotency_key: str,
) -> None:
    """Apply the command limit only to an anonymous actor inside the locked demo."""

    if context.demo_run_id is None or not context.actor.is_anonymous:
        return
    try:
        limiter.admit(str(context.actor.user_id), idempotency_key)
    except DemoAiCommandRateLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "This demo has received too many new AI requests. "
                f"Retry in {error.retry_after_seconds} seconds."
            ),
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
