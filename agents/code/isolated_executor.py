"""
agents/code/isolated_executor.py
================================
Supervised subprocess executor for Code Agent runs (KOS-012).
"""

from __future__ import annotations

import os
import sys
from typing import Any

from runtime.ipc import IpcError, JsonLineClient, spawn_worker


class IsolatedCodeExecutor:
    """Runs code verification in a supervised worker subprocess."""

    def __init__(self) -> None:
        self._worker_cmd = [sys.executable, "-m", "agents.code.subprocess_runner"]
        self._client: JsonLineClient | None = None
        self._start_worker()

    def _start_worker(self) -> None:
        proc = spawn_worker(self._worker_cmd)
        self._client = JsonLineClient(proc)
        try:
            self._client.call("ping", timeout=5)
        except Exception:
            self._restart_worker(reason="ping failed on startup")

    def _restart_worker(self, reason: str) -> None:
        try:
            from kernel.decision_log import record_decision

            record_decision(
                actor="code_executor",
                decision_type="worker_restart",
                input_summary="agents.code.subprocess_runner",
                outcome="restarted",
                reason=reason,
            )
        except Exception:
            pass

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        proc = spawn_worker(self._worker_cmd)
        self._client = JsonLineClient(proc)

    def run_and_verify(self, path: str) -> dict[str, Any]:
        if not self._client:
            self._start_worker()
        try:
            result = self._client.call("run_file", {"path": path})
            if isinstance(result, dict):
                return result
            return {"ran": False, "reason": "invalid worker response"}
        except IpcError as exc:
            self._restart_worker(str(exc))
            try:
                result = self._client.call("run_file", {"path": path})
                if isinstance(result, dict):
                    return result
            except Exception as retry_exc:
                return {"ran": False, "reason": str(retry_exc)}
            return {"ran": False, "reason": str(exc)}

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None


_executor: IsolatedCodeExecutor | None = None


def get_isolated_executor() -> IsolatedCodeExecutor:
    global _executor
    if _executor is None:
        _executor = IsolatedCodeExecutor()
    return _executor
