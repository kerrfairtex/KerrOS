"""
execution/safe_executor.py
===========================
Compatibility wrapper around ``execution.executor.SandboxExecutor``.

Prefer ``SandboxExecutor`` directly for new code.
"""

from __future__ import annotations

from typing import Any

from execution.executor import SandboxExecutor


class SafeExecutor:
    def __init__(self, timeout: int = 30, mem_mb: int = 512) -> None:
        self._executor = SandboxExecutor(timeout=timeout, mem_mb=mem_mb)

    def execute(self, cmd: list[str] | str) -> dict[str, Any]:
        if isinstance(cmd, str):
            cmd = [cmd]
        try:
            output = self._executor.run(cmd)
            return {"stdout": output, "stderr": "", "code": 0}
        except ValueError as exc:
            return {"error": str(exc), "stdout": "", "stderr": "", "code": 2}
        except RuntimeError as exc:
            return {"error": str(exc), "stdout": "", "stderr": "", "code": 1}
        except Exception as exc:
            return {"error": str(exc), "stdout": "", "stderr": "", "code": 1}
