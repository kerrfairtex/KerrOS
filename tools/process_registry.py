"""
tools/process_registry.py
=========================
In-memory registry for managed background processes (ADR-063).

Tracks subprocesses spawned for long jobs (tests, builds) without blocking
the REPL. Output is a rolling buffer. Default max 8 concurrent.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.interrupt import is_interrupted

MAX_OUTPUT_CHARS = 100_000
MAX_PROCESSES = 8
FINISHED_TTL_SECONDS = 1800


@dataclass
class ProcessSession:
    id: str
    command: str
    proc: Any = None
    status: str = "running"  # running | exited | killed | error
    returncode: Optional[int] = None
    output: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: str = ""


class ProcessRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._procs: dict[str, ProcessSession] = {}

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
        # Cap total
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
            session = ProcessSession(id=sid, command=cmd)
            try:
                session.proc = subprocess.Popen(
                    cmd,
                    shell=True,
                    cwd=cwd or os.getcwd(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as exc:
                session.status = "error"
                session.error = str(exc)
                session.finished_at = time.time()
                self._procs[sid] = session
                return {"ok": False, "id": sid, "error": str(exc)}

            self._procs[sid] = session
            threading.Thread(target=self._reader, args=(sid,), daemon=True).start()
            return {"ok": True, "id": sid, "command": cmd}

    def _reader(self, sid: str) -> None:
        with self._lock:
            session = self._procs.get(sid)
            proc = session.proc if session else None
        if not session or not proc or not proc.stdout:
            return
        try:
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
                    s.status = "exited" if rc != -2 else "killed"
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
            return {
                "ok": True,
                "id": s.id,
                "status": s.status,
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
            if s.proc and s.status == "running":
                try:
                    s.proc.terminate()
                    try:
                        s.proc.wait(timeout=3)
                    except Exception:
                        s.proc.kill()
                except Exception as exc:
                    s.error = str(exc)
                s.status = "killed"
                s.finished_at = time.time()
            return self.poll(sid)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            return [
                {
                    "id": s.id,
                    "status": s.status,
                    "command": s.command[:120],
                    "returncode": s.returncode,
                    "uptime_s": int(time.time() - s.started_at),
                }
                for s in self._procs.values()
            ]


process_registry = ProcessRegistry()


def bg_process(action: str, raw: str = "") -> str:
    """Router helper: spawn|poll|wait|kill|list."""
    action = (action or "list").strip().lower()
    arg = (raw or "").strip()
    if action == "list":
        items = process_registry.list()
        if not items:
            return "[bg] no processes"
        lines = ["[bg] processes:"]
        for it in items:
            lines.append(f"- {it['id']} [{it['status']}] {it['command']}")
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
