"""
tools/process_registry.py
=========================
In-memory registry for managed background processes (ADR-063/064).

Tracks subprocesses spawned for long jobs without blocking the REPL.
Backends: local | fake | docker | remote (see process_backends.py).
"""

from __future__ import annotations

import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.interrupt import is_interrupted
from tools.process_backends import get_backend, resolve_backend_name

MAX_OUTPUT_CHARS = 100_000
MAX_PROCESSES = 8
FINISHED_TTL_SECONDS = 1800


@dataclass
class ProcessSession:
    id: str
    command: str
    backend: str = "local"
    handle: Any = None
    status: str = "running"
    returncode: Optional[int] = None
    output: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: str = ""


class ProcessRegistry:
    def __init__(self, backend_name: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._procs: dict[str, ProcessSession] = {}
        self._backend_name = backend_name or resolve_backend_name()
        self._backend = get_backend(self._backend_name)

    def _prune(self) -> None:
        now = time.time()
        dead = [
            pid
            for pid, s in self._procs.items()
            if s.status != "running"
            and s.finished_at
            and now - float(s.finished_at) > FINISHED_TTL_SECONDS
        ]
        for pid in dead:
            self._procs.pop(pid, None)
        if len(self._procs) > MAX_PROCESSES:
            finished = sorted(
                (s for s in self._procs.values() if s.status != "running"),
                key=lambda s: s.finished_at or 0,
            )
            for s in finished[: max(0, len(self._procs) - MAX_PROCESSES)]:
                self._procs.pop(s.id, None)

    def spawn(self, command: str, *, cwd: Optional[str] = None) -> dict[str, Any]:
        cmd = (command or "").strip()
        if not cmd:
            return {"ok": False, "error": "command required"}
        with self._lock:
            active = sum(1 for s in self._procs.values() if s.status == "running")
            if active >= MAX_PROCESSES:
                return {"ok": False, "error": f"max {MAX_PROCESSES} concurrent processes"}
            self._prune()
            sid = uuid.uuid4().hex[:10]
            session = ProcessSession(id=sid, command=cmd, backend=self._backend.name)
            handle = self._backend.spawn(cmd, cwd=cwd)
            session.handle = handle
            session.output = handle.output or ""
            session.status = handle.status
            session.returncode = handle.returncode
            if handle.status != "running":
                session.finished_at = time.time()
                if handle.status == "error":
                    session.error = handle.output
                    self._procs[sid] = session
                    return {"ok": False, "id": sid, "error": session.error, "backend": session.backend}
                self._procs[sid] = session
                return {
                    "ok": True,
                    "id": sid,
                    "command": cmd,
                    "backend": session.backend,
                    "status": session.status,
                }
            self._procs[sid] = session
            threading.Thread(target=self._reader, args=(sid,), daemon=True).start()
            return {"ok": True, "id": sid, "command": cmd, "backend": session.backend}

    def _reader(self, sid: str) -> None:
        with self._lock:
            session = self._procs.get(sid)
            handle = session.handle if session else None
            proc = getattr(handle, "_proc", None) if handle else None
        if not session or not handle:
            return
        # Fake/docker-soft already finished
        if session.status != "running" or proc is None:
            return
        try:
            if proc.stdout:
                for line in proc.stdout:
                    if is_interrupted():
                        try:
                            proc.send_signal(signal.SIGINT)
                        except Exception:
                            pass
                        break
                    with self._lock:
                        s = self._procs.get(sid)
                        if not s:
                            break
                        s.output = (s.output + line)[-MAX_OUTPUT_CHARS:]
            rc = proc.wait()
            with self._lock:
                s = self._procs.get(sid)
                if s:
                    s.returncode = rc
                    s.status = "killed" if is_interrupted() else "exited"
                    s.finished_at = time.time()
        except Exception as exc:
            with self._lock:
                s = self._procs.get(sid)
                if s:
                    s.status = "error"
                    s.error = str(exc)
                    s.finished_at = time.time()

    def poll(self, sid: str) -> dict[str, Any]:
        with self._lock:
            s = self._procs.get(sid)
            if not s:
                return {"ok": False, "error": "unknown process id"}
            if s.handle is not None and s.status == "running":
                self._backend.poll(s.handle)
                s.status = s.handle.status
                s.returncode = s.handle.returncode
                if s.handle.output and not s.output:
                    s.output = s.handle.output
                if s.status != "running" and not s.finished_at:
                    s.finished_at = time.time()
            return {
                "ok": True,
                "id": s.id,
                "status": s.status,
                "backend": s.backend,
                "returncode": s.returncode,
                "command": s.command,
                "output_tail": s.output[-2000:],
                "error": s.error,
                "uptime_s": int(time.time() - s.started_at),
            }

    def wait(self, sid: str, *, timeout: float = 300) -> dict[str, Any]:
        deadline = time.time() + max(1.0, float(timeout))
        while time.time() < deadline:
            if is_interrupted():
                self.kill(sid)
                return self.poll(sid)
            info = self.poll(sid)
            if not info.get("ok"):
                return info
            if info.get("status") != "running":
                return info
            time.sleep(0.2)
        return {"ok": False, "error": "timeout", "id": sid, **{k: v for k, v in self.poll(sid).items() if k != "ok"}}

    def kill(self, sid: str) -> dict[str, Any]:
        with self._lock:
            s = self._procs.get(sid)
            if not s:
                return {"ok": False, "error": "unknown process id"}
            if s.handle is not None and s.status == "running":
                self._backend.kill(s.handle)
                s.status = "killed"
                s.finished_at = time.time()
                s.returncode = s.handle.returncode
            return self.poll(sid)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            return [
                {
                    "id": s.id,
                    "status": s.status,
                    "backend": s.backend,
                    "command": s.command[:120],
                    "returncode": s.returncode,
                    "uptime_s": int(time.time() - s.started_at),
                }
                for s in self._procs.values()
            ]


process_registry = ProcessRegistry()


def bg_process(action: str, raw: str = "") -> str:
    action = (action or "list").strip().lower()
    arg = (raw or "").strip()
    if action == "list":
        items = process_registry.list()
        if not items:
            return f"[bg] no processes (backend={process_registry._backend_name})"
        lines = [f"[bg] processes (backend={process_registry._backend_name}):"]
        for it in items:
            lines.append(f"- {it['id']} [{it['status']}/{it.get('backend')}] {it['command']}")
        return "\n".join(lines)
    if action == "spawn":
        if not arg:
            return "[bg] usage: bg spawn <command>"
        return str(process_registry.spawn(arg))
    if action == "poll" and arg:
        return str(process_registry.poll(arg))
    if action == "wait" and arg:
        return str(process_registry.wait(arg))
    if action == "kill" and arg:
        return str(process_registry.kill(arg))
    return "[bg] actions: list|spawn|poll|wait|kill"
