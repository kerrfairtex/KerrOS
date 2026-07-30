"""
gateway/channels/trace.py
=========================
Persisted Soft trace buffer for channel/TUI events (ADR-087).

Append-only JSONL under data/channel_trace.jsonl (capped).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()
BASE = Path(os.path.expanduser("~/offline_ai"))
TRACE_PATH = BASE / "data" / "channel_trace.jsonl"
MAX_LINES = 2000


def _path() -> Path:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return TRACE_PATH


def append_trace(kind: str, detail: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "kind": str(kind or "event"),
        "detail": detail or {},
    }
    with _lock:
        p = _path()
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        # Cap file size by rewriting tail when large
        try:
            if p.stat().st_size > 1_500_000:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                p.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
        except Exception:
            pass
    return row


def read_trace(limit: int = 40) -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, min(int(limit), 500)) :]:
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                out.append(row)
        except Exception:
            continue
    return out


def clear_trace() -> None:
    with _lock:
        p = _path()
        if p.exists():
            p.write_text("", encoding="utf-8")


def format_trace(limit: int = 20) -> str:
    rows = read_trace(limit=limit)
    if not rows:
        return "[trace] empty"
    lines = [f"[trace] {len(rows)} event(s):"]
    for r in rows:
        det = r.get("detail") or {}
        extra = ""
        if isinstance(det, dict) and det:
            extra = " " + json.dumps(det, ensure_ascii=False)[:120]
        lines.append(f"- {r.get('ts')} · {r.get('kind')}{extra}")
    return "\n".join(lines)
