from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from threading import Event
from typing import IO, Protocol

EXPIRED_SESSION_TEXT = "Unauthorized: Tunnel not found"
BASE_RESTART_DELAY_SECONDS = 2.0
MAX_RESTART_DELAY_SECONDS = 60.0
STABLE_SESSION_SECONDS = 300.0
GRACEFUL_EXIT_SECONDS = 10.0


class ChildProcess(Protocol):
    stdout: IO[str] | None
    returncode: int | None

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, separators=(",", ":")), flush=True)


def restart_delay(
    consecutive_restarts: int,
    *,
    base_seconds: float = BASE_RESTART_DELAY_SECONDS,
    maximum_seconds: float = MAX_RESTART_DELAY_SECONDS,
) -> float:
    # Capping the exponent also avoids constructing arbitrarily large integers
    # if an upstream session remains unavailable for a long time.
    return min(base_seconds * (2 ** min(consecutive_restarts, 16)), maximum_seconds)


class TunnelSupervisor:
    def __init__(
        self,
        command: Sequence[str],
        *,
        spawn: Callable[[Sequence[str]], ChildProcess] | None = None,
        clock: Callable[[], float] = time.monotonic,
        stop: Event | None = None,
        output: IO[str] = sys.stdout,
        graceful_exit_seconds: float = GRACEFUL_EXIT_SECONDS,
    ) -> None:
        if not command:
            raise ValueError("cloudflared command is required")
        self._command = tuple(command)
        self._spawn = spawn or self._spawn_child
        self._clock = clock
        self._stop = stop or Event()
        self._output = output
        self._graceful_exit_seconds = graceful_exit_seconds
        self._child: ChildProcess | None = None

    @staticmethod
    def _spawn_child(command: Sequence[str]) -> ChildProcess:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    def request_stop(self) -> None:
        self._stop.set()
        child = self._child
        if child is not None and child.returncode is None:
            child.terminate()

    def _finish_child(self, child: ChildProcess) -> int:
        try:
            return child.wait(timeout=self._graceful_exit_seconds)
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait()

    def run(self) -> int:
        consecutive_restarts = 0
        while not self._stop.is_set():
            started_at = self._clock()
            try:
                child = self._spawn(self._command)
            except OSError:
                emit("tunnel.child_start_failed")
                return 127
            self._child = child
            expired_session = False
            try:
                if child.stdout is None:
                    raise RuntimeError("cloudflared output pipe is unavailable")
                for line in child.stdout:
                    self._output.write(line)
                    self._output.flush()
                    if not expired_session and EXPIRED_SESSION_TEXT in line:
                        expired_session = True
                        emit("tunnel.expired_session_restart")
                        child.terminate()
                exit_code = self._finish_child(child)
            finally:
                self._child = None

            if self._stop.is_set():
                return 0
            if not expired_session:
                # Ordinary DNS, TLS, QUIC and timeout failures remain cloudflared's
                # responsibility. If cloudflared exits, Docker's restart policy
                # restarts this container without misclassifying the cause.
                return exit_code if exit_code != 0 else 1

            if self._clock() - started_at >= STABLE_SESSION_SECONDS:
                consecutive_restarts = 0
            delay_seconds = restart_delay(consecutive_restarts)
            consecutive_restarts += 1
            emit("tunnel.expired_session_backoff", delay_seconds=delay_seconds)
            if self._stop.wait(delay_seconds):
                return 0
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("cloudflared arguments are required", file=sys.stderr)
        return 2
    supervisor = TunnelSupervisor(("/usr/local/bin/cloudflared", *arguments))

    def stop(_signum: int, _frame: object) -> None:
        supervisor.request_stop()

    for signal_name in ("SIGTERM", "SIGINT"):
        candidate = getattr(signal, signal_name, None)
        if candidate is not None:
            signal.signal(candidate, stop)
    return supervisor.run()


if __name__ == "__main__":
    raise SystemExit(main())
