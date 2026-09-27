from __future__ import annotations

import io
import subprocess
import unittest
from collections.abc import Sequence
from threading import Event

from supervisor import TunnelSupervisor, restart_delay


class FakeProcess:
    def __init__(
        self, lines: Sequence[str], *, exit_code: int = 0, ignore_term: bool = False
    ) -> None:
        self.stdout = io.StringIO("".join(lines))
        self.returncode: int | None = None
        self._exit_code = exit_code
        self._ignore_term = ignore_term
        self.terminations = 0
        self.kills = 0

    def terminate(self) -> None:
        self.terminations += 1
        if not self._ignore_term:
            self.returncode = self._exit_code

    def kill(self) -> None:
        self.kills += 1
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.returncode is None:
            if self._ignore_term and timeout is not None:
                raise subprocess.TimeoutExpired("cloudflared", timeout)
            self.returncode = self._exit_code
        return self.returncode


class RecordingStop(Event):
    def __init__(self, *, stop_after_waits: int | None = None) -> None:
        super().__init__()
        self.delays: list[float] = []
        self._stop_after_waits = stop_after_waits

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is not None:
            self.delays.append(timeout)
        if (
            self._stop_after_waits is not None
            and len(self.delays) >= self._stop_after_waits
        ):
            self.set()
        return self.is_set()


class TunnelSupervisorTests(unittest.TestCase):
    def test_exact_expired_session_restarts_only_cloudflared_child(self) -> None:
        expired = FakeProcess(
            ['ERR Register tunnel error error="Unauthorized: Tunnel not found"\n']
        )
        healthy_exit = FakeProcess(["Registered tunnel connection\n"], exit_code=7)
        processes = iter((expired, healthy_exit))
        stop = RecordingStop()
        supervisor = TunnelSupervisor(
            ("cloudflared", "tunnel"),
            spawn=lambda _command: next(processes),
            stop=stop,
            output=io.StringIO(),
        )

        self.assertEqual(supervisor.run(), 7)
        self.assertEqual(expired.terminations, 1)
        self.assertEqual(healthy_exit.terminations, 0)
        self.assertEqual(stop.delays, [2.0])

    def test_generic_network_failures_do_not_trigger_internal_restart(self) -> None:
        for line in (
            "lookup region1.v2.argotunnel.com: i/o timeout\n",
            "datagram manager error: timeout: no recent network activity\n",
            "TLS handshake timeout\n",
            "Unauthorized: invalid token\n",
        ):
            with self.subTest(line=line):
                process = FakeProcess([line], exit_code=8)
                spawn_count = 0

                def spawn(
                    _command: Sequence[str], selected: FakeProcess = process
                ) -> FakeProcess:
                    nonlocal spawn_count
                    spawn_count += 1
                    return selected

                supervisor = TunnelSupervisor(
                    ("cloudflared", "tunnel"),
                    spawn=spawn,
                    output=io.StringIO(),
                )
                self.assertEqual(supervisor.run(), 8)
                self.assertEqual(spawn_count, 1)
                self.assertEqual(process.terminations, 0)

    def test_restart_backoff_is_capped(self) -> None:
        self.assertEqual(
            [restart_delay(attempt) for attempt in range(7)], [2, 4, 8, 16, 32, 60, 60]
        )
        self.assertEqual(restart_delay(1_000_000), 60)

    def test_stop_during_backoff_prevents_another_child(self) -> None:
        expired = FakeProcess(["Unauthorized: Tunnel not found\n"])
        stop = RecordingStop(stop_after_waits=1)
        spawn_count = 0

        def spawn(_command: Sequence[str]) -> FakeProcess:
            nonlocal spawn_count
            spawn_count += 1
            return expired

        supervisor = TunnelSupervisor(
            ("cloudflared", "tunnel"),
            spawn=spawn,
            stop=stop,
            output=io.StringIO(),
        )

        self.assertEqual(supervisor.run(), 0)
        self.assertEqual(spawn_count, 1)

    def test_signal_request_gracefully_terminates_current_child(self) -> None:
        process = FakeProcess([], exit_code=0)
        supervisor = TunnelSupervisor(
            ("cloudflared", "tunnel"),
            spawn=lambda _command: process,
            output=io.StringIO(),
        )
        supervisor._child = process

        supervisor.request_stop()

        self.assertTrue(supervisor._stop.is_set())
        self.assertEqual(process.terminations, 1)

    def test_unresponsive_child_is_killed_after_grace_period(self) -> None:
        process = FakeProcess(["Unauthorized: Tunnel not found\n"], ignore_term=True)
        stop = RecordingStop(stop_after_waits=1)
        supervisor = TunnelSupervisor(
            ("cloudflared", "tunnel"),
            spawn=lambda _command: process,
            stop=stop,
            output=io.StringIO(),
            graceful_exit_seconds=0.01,
        )

        self.assertEqual(supervisor.run(), 0)
        self.assertEqual(process.kills, 1)


if __name__ == "__main__":
    unittest.main()
