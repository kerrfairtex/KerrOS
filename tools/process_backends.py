"""
tools/process_backends.py
=========================
Execution backends for background processes (ADR-064).

Backends:
  - local  — host subprocess (default)
  - fake   — no real spawn; records command and completes instantly (CI)
  - docker — Soft plan/stub unless KERROS_BG_DOCKER=1 and docker available
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_backend_name(cfg: Optional[dict] = None) -> str:
    env = (os.environ.get("KERROS_BG_BACKEND") or "").strip().lower()
    if env in ("local", "fake", "docker"):
        return env
    block = (cfg or {}).get("bg_process") if isinstance((cfg or {}).get("bg_process"), dict) else {}
    name = str(block.get("backend") or "local").strip().lower()
    return name if name in ("local", "fake", "docker") else "local"


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


def get_backend(name: Optional[str] = None) -> Any:
    n = (name or resolve_backend_name()).lower()
    if n == "fake":
        return FakeBackend()
    if n == "docker":
        return DockerBackend()
    return LocalBackend()
