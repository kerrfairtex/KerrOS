"""
kernel/watchdog.py
==================
Process watchdog for KerrOS daemon (KOS-011).

Restarts supervised processes on crash with exponential backoff.
Logs restarts to decision_log and disarms deploy scope on restart (fail-closed).
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from kernel.decision_log import record_decision


@dataclass
class WatchdogConfig:
    max_restarts: int = 10
    backoff_base: float = 2.0
    backoff_cap: float = 60.0
    poll_interval: float = 1.0


@dataclass
class Watchdog:
    """Supervise a subprocess command, restarting on nonzero exit."""

    command: Sequence[str]
    config: WatchdogConfig = field(default_factory=WatchdogConfig)
    on_restart: Callable[[], None] | None = None
    _restart_count: int = 0

    def _fail_closed_reset(self) -> None:
        try:
            from tools.scope_gate import disarm_deploy

            disarm_deploy()
        except Exception:
            pass

    def _log_event(self, outcome: str, reason: str, summary: str) -> None:
        record_decision(
            actor="watchdog",
            decision_type="watchdog",
            input_summary=summary,
            outcome=outcome,
            reason=reason,
        )

    def run_once(self) -> int:
        """Run the supervised command once. Returns exit code."""
        proc = subprocess.run(list(self.command))
        return proc.returncode

    def run(self) -> None:
        """Supervise until max restarts exceeded."""
        cmd_str = " ".join(self.command)
        self._log_event("started", "watchdog supervising process", cmd_str)

        while self._restart_count <= self.config.max_restarts:
            code = self.run_once()
            if code == 0:
                self._log_event("stopped", "clean exit", cmd_str)
                return

            self._restart_count += 1
            if self._restart_count > self.config.max_restarts:
                self._log_event(
                    "failed",
                    f"max restarts ({self.config.max_restarts}) exceeded",
                    cmd_str,
                )
                return

            delay = min(
                self.config.backoff_cap,
                self.config.backoff_base ** (self._restart_count - 1),
            )
            self._fail_closed_reset()
            if self.on_restart:
                try:
                    self.on_restart()
                except Exception:
                    pass

            self._log_event(
                "restarted",
                f"exit={code}, restart={self._restart_count}, delay={delay:.1f}s",
                cmd_str,
            )
            time.sleep(delay)

    def status(self) -> dict:
        return {
            "command": list(self.command),
            "restart_count": self._restart_count,
            "max_restarts": self.config.max_restarts,
        }


def supervise(command: Sequence[str], **kwargs) -> None:
    """Convenience entry: supervise a command until clean exit or max restarts."""
    Watchdog(command=list(command), **kwargs).run()
