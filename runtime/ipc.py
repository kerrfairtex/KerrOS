"""
runtime/ipc.py
==============
JSON-line IPC protocol for subprocess workers (KOS-012).

Request:  {"id": "...", "method": "...", "params": {...}}
Response: {"id": "...", "ok": true, "result": ...}
       or {"id": "...", "ok": false, "error": "..."}
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from typing import Any


class IpcError(Exception):
    pass


def encode_message(msg_id: str, method: str, params: dict[str, Any] | None = None) -> str:
    return json.dumps({"id": msg_id, "method": method, "params": params or {}}) + "\n"


def decode_message(line: str) -> dict[str, Any]:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise IpcError("message must be a JSON object")
    return data


def encode_response(msg_id: str, ok: bool, result: Any = None, error: str = "") -> str:
    payload: dict[str, Any] = {"id": msg_id, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error
    return json.dumps(payload) + "\n"


class JsonLineClient:
    """Send one request to a long-lived subprocess and read one response."""

    def __init__(self, proc: subprocess.Popen) -> None:
        self.proc = proc
        if not self.proc.stdin or not self.proc.stdout:
            raise IpcError("subprocess missing stdin/stdout pipes")

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30) -> Any:
        msg_id = str(uuid.uuid4())
        line = encode_message(msg_id, method, params)
        self.proc.stdin.write(line)
        self.proc.stdin.flush()

        if self.proc.poll() is not None:
            raise IpcError(f"worker exited before response (code={self.proc.returncode})")

        response_line = self.proc.stdout.readline()
        if not response_line:
            raise IpcError("worker closed stdout without response")

        data = decode_message(response_line)
        if data.get("id") != msg_id:
            raise IpcError(f"response id mismatch: expected {msg_id}, got {data.get('id')}")
        if not data.get("ok"):
            raise IpcError(data.get("error") or "unknown worker error")
        return data.get("result")

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def spawn_worker(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
