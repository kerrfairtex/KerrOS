"""
tools/process_backends.py
=========================
Execution backends for background processes (ADR-064).

Backends:
  - local  — host subprocess (default)
  - fake   — no real spawn; records command and completes instantly (CI)
  - docker — Soft plan/stub unless KERROS_BG_DOCKER=1 and docker available
  - remote — Soft remote sandbox fleet (ADR-077); live HTTP when
             KERROS_REMOTE_SANDBOX=1 and KERROS_REMOTE_SANDBOX_URL is set
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

_BACKEND_NAMES = ("local", "fake", "docker", "remote")


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_backend_name(cfg: Optional[dict] = None) -> str:
    env = (os.environ.get("KERROS_BG_BACKEND") or "").strip().lower()
    if env in _BACKEND_NAMES:
        return env
    block = (cfg or {}).get("bg_process") if isinstance((cfg or {}).get("bg_process"), dict) else {}
    name = str(block.get("backend") or "local").strip().lower()
    return name if name in _BACKEND_NAMES else "local"


@dataclass
class BackendHandle:
    pid: Optional[int] = None
    returncode: Optional[int] = None
    output: str = ""
    status: str = "running"  # running | exited | error
    meta: dict[str, Any] = field(default_factory=dict)
    _proc: Any = None


class ProcessBackend(Protocol):
    name: str

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> BackendHandle: ...
    def poll(self, handle: BackendHandle) -> BackendHandle: ...
    def kill(self, handle: BackendHandle) -> BackendHandle: ...


class LocalBackend:
    name = "local"

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> BackendHandle:
        h = BackendHandle()
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=cwd or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            h._proc = proc
            h.pid = proc.pid
            h.meta["backend"] = self.name
        except Exception as exc:
            h.status = "error"
            h.output = str(exc)
            h.returncode = 1
        return h

    def poll(self, handle: BackendHandle) -> BackendHandle:
        proc = handle._proc
        if proc is None:
            return handle
        if proc.poll() is None:
            # drain available
            try:
                if proc.stdout:
                    # non-blocking-ish read not portable; leave reader thread to registry
                    pass
            except Exception:
                pass
            handle.status = "running"
            return handle
        handle.returncode = proc.returncode
        handle.status = "exited"
        return handle

    def kill(self, handle: BackendHandle) -> BackendHandle:
        proc = handle._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()
            except Exception as exc:
                handle.output += f"\n[kill error] {exc}"
        handle.status = "exited"
        handle.returncode = handle.returncode if handle.returncode is not None else -9
        return handle


class FakeBackend:
    name = "fake"

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> BackendHandle:
        return BackendHandle(
            pid=0,
            returncode=0,
            output=f"[fake] completed: {command}\n",
            status="exited",
            meta={"backend": "fake", "cwd": cwd or os.getcwd()},
        )

    def poll(self, handle: BackendHandle) -> BackendHandle:
        handle.status = "exited"
        handle.returncode = 0
        return handle

    def kill(self, handle: BackendHandle) -> BackendHandle:
        handle.status = "exited"
        handle.returncode = -9
        handle.output += "\n[fake] killed"
        return handle


class DockerBackend:
    """Soft docker backend — plans unless KERROS_BG_DOCKER=1 and docker exists."""

    name = "docker"

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> BackendHandle:
        allow = _truthy(os.environ.get("KERROS_BG_DOCKER"))
        docker = shutil.which("docker")
        if not allow or not docker:
            return BackendHandle(
                status="exited",
                returncode=0,
                output=(
                    "[docker soft] would run via docker; set KERROS_BG_DOCKER=1 "
                    "and install docker for live. command=" + command
                ),
                meta={"backend": "docker", "soft": True},
            )
        # Minimal live: docker run --rm alpine sh -c
        image = os.environ.get("KERROS_BG_DOCKER_IMAGE") or "alpine:3.20"
        argv = [docker, "run", "--rm", image, "sh", "-c", command]
        h = BackendHandle(meta={"backend": "docker", "soft": False, "image": image})
        try:
            proc = subprocess.Popen(
                argv,
                cwd=cwd or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            h._proc = proc
            h.pid = proc.pid
        except Exception as exc:
            h.status = "error"
            h.output = str(exc)
            h.returncode = 1
        return h

    def poll(self, handle: BackendHandle) -> BackendHandle:
        return LocalBackend().poll(handle)

    def kill(self, handle: BackendHandle) -> BackendHandle:
        return LocalBackend().kill(handle)


class RemoteSandboxBackend:
    """
    Soft remote sandbox fleet (ADR-077).

    Default Soft plan. Live POST to KERROS_REMOTE_SANDBOX_URL when
    KERROS_REMOTE_SANDBOX=1. Expected JSON response:
      {"ok": true, "output": "...", "exit_code": 0}
    """

    name = "remote"

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> BackendHandle:
        allow = _truthy(os.environ.get("KERROS_REMOTE_SANDBOX"))
        url = (os.environ.get("KERROS_REMOTE_SANDBOX_URL") or "").strip()
        if not allow or not url:
            return BackendHandle(
                status="exited",
                returncode=0,
                output=(
                    "[remote soft] would run on remote sandbox fleet; set "
                    "KERROS_REMOTE_SANDBOX=1 and KERROS_REMOTE_SANDBOX_URL. "
                    f"command={command}"
                ),
                meta={"backend": "remote", "soft": True, "cwd": cwd or os.getcwd()},
            )
        payload = json.dumps(
            {
                "command": command,
                "cwd": cwd or os.getcwd(),
                "source": "kerros-bg",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "KerrOS-RemoteSandbox (ADR-077)",
            },
        )
        token = (os.environ.get("KERROS_REMOTE_SANDBOX_TOKEN") or "").strip()
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
            ok = bool(data.get("ok", True))
            return BackendHandle(
                status="exited",
                returncode=int(data.get("exit_code") or (0 if ok else 1)),
                output=str(data.get("output") or raw)[:8000],
                meta={"backend": "remote", "soft": False, "url": url},
            )
        except Exception as exc:
            return BackendHandle(
                status="error",
                returncode=1,
                output=f"[remote] {exc}",
                meta={"backend": "remote", "soft": False, "url": url},
            )

    def poll(self, handle: BackendHandle) -> BackendHandle:
        if handle.status == "running":
            handle.status = "exited"
            handle.returncode = handle.returncode if handle.returncode is not None else 0
        return handle

    def kill(self, handle: BackendHandle) -> BackendHandle:
        handle.status = "exited"
        handle.returncode = handle.returncode if handle.returncode is not None else -9
        handle.output += "\n[remote] kill requested"
        return handle


def get_backend(name: Optional[str] = None) -> Any:
    n = (name or resolve_backend_name()).lower()
    if n == "fake":
        return FakeBackend()
    if n == "docker":
        return DockerBackend()
    if n == "remote":
        return RemoteSandboxBackend()
    return LocalBackend()
