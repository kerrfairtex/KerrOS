"""
execution/executor.py
=====================
Restricted command execution helper.

Public entry points:
    - SandboxExecutor.run(command: list[str]) -> str
    - restricted_run(command: list[str]) -> dict[str, Any]
"""

from __future__ import annotations

import platform
import resource
import subprocess
from typing import Any


class SandboxExecutor:
    PERMITTED_BINS = {
        "arp",
        "curl",
        "df",
        "dig",
        "exiftool",
        "file",
        "free",
        "gh",
        "git",
        "host",
        "ip",
        "ls",
        "netstat",
        "nikto",
        "nmap",
        "openssl",
        "ping",
        "railway",
        "sleep",
        "ss",
        "strings",
        "stripe",
        "supabase",
        "traceroute",
        "whois",
        "wrangler",
    }

    def __init__(self, timeout: int = 30, mem_mb: int = 512) -> None:
        self.timeout = timeout
        self.mem_mb = mem_mb

    def _set_limits(self) -> None:
        if platform.system() != "Windows":
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.mem_mb * 1024 * 1024, self.mem_mb * 1024 * 1024),
            )
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.timeout, self.timeout + 5),
            )

    def run(self, cmd: list[str], cwd: str | None = None, env: dict | None = None) -> str:
        if not cmd:
            raise ValueError("command is required")
        if cmd[0] not in self.PERMITTED_BINS:
            raise ValueError(f"Command '{cmd[0]}' not in allowlist")

        kwargs: dict[str, Any] = {
            "args": cmd,
            "cwd": cwd,
            "env": env,
            "capture_output": True,
            "text": True,
            "timeout": self.timeout,
            "shell": False,
        }
        if platform.system() != "Windows":
            kwargs["preexec_fn"] = self._set_limits
        else:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        try:
            result = subprocess.run(**kwargs)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Command timed out after {self.timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Command failed ({exc.returncode}): {exc.stderr}") from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"Command failed ({result.returncode}): {result.stderr.strip()}"
            )

        return result.stdout.strip()


def restricted_run(command: list[str], *, timeout: int = 30, mem_mb: int = 512) -> dict[str, Any]:
    """Run a command through restricted execution and return a normalized result."""
    executor = SandboxExecutor(timeout=timeout, mem_mb=mem_mb)
    try:
        output = executor.run(command)
        return {"stdout": output, "stderr": "", "code": 0}
    except ValueError as exc:
        return {"error": str(exc), "stdout": "", "stderr": "", "code": 2}
    except RuntimeError as exc:
        return {"error": str(exc), "stdout": "", "stderr": "", "code": 1}
    except Exception as exc:
        return {"error": str(exc), "stdout": "", "stderr": "", "code": 1}
