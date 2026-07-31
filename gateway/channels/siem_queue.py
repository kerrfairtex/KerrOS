"""
gateway/channels/siem_queue.py
==============================
Durable Soft SIEM push retry/backoff queue (ADR-097).

Failed pushes are appended to data/siem_queue.jsonl and drained with
exponential backoff via flush_siem_queue().
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()
BASE = Path(os.path.expanduser("~/offline_ai"))
QUEUE_PATH = BASE / "data" / "siem_queue.jsonl"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _path() -> Path:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return QUEUE_PATH


def enqueue_failed(
    *,
    format: str,
    body: bytes,
    content_type: str,
    error: str,
    attempts: int = 0,
) -> dict[str, Any]:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "format": format,
        "content_type": content_type,
        "body_b64": __import__("base64").b64encode(body).decode("ascii"),
        "error": str(error)[:500],
        "attempts": int(attempts),
        "next_at": time.time() + min(300, 2 ** max(0, int(attempts))),
    }
    with _lock:
        with _path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    return {"ok": True, "queued": True, "attempts": row["attempts"], "next_at": row["next_at"]}


def _load_rows() -> list[dict[str, Any]]:
    p = _path()
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
        except Exception:
            continue
    return rows


def _save_rows(rows: list[dict[str, Any]]) -> None:
    p = _path()
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def queue_status() -> dict[str, Any]:
    rows = _load_rows()
    return {"ok": True, "pending": len(rows), "oldest": rows[0].get("ts") if rows else None}


def flush_siem_queue(*, max_items: int = 20) -> dict[str, Any]:
    """Attempt to deliver due Soft queue items."""
    url = (os.environ.get("KERROS_SIEM_URL") or "").strip()
    if not url or not _truthy(os.environ.get("KERROS_SIEM_PUSH")):
        return {
            "ok": True,
            "soft": True,
            "flushed": 0,
            "pending": len(_load_rows()),
            "note": "SIEM push disabled — queue retained",
        }
    import base64

    now = time.time()
    kept: list[dict[str, Any]] = []
    flushed = 0
    errors = 0
    with _lock:
        rows = _load_rows()
        for row in rows:
            if flushed >= max_items:
                kept.append(row)
                continue
            if float(row.get("next_at") or 0) > now:
                kept.append(row)
                continue
            try:
                body = base64.b64decode(row.get("body_b64") or "")
            except Exception:
                errors += 1
                continue
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": str(row.get("content_type") or "application/json"),
                    "User-Agent": "KerrOS-SIEMQueue (ADR-097)",
                },
            )
            token = (os.environ.get("KERROS_SIEM_TOKEN") or "").strip()
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp.read()
                flushed += 1
            except Exception as exc:
                attempts = int(row.get("attempts") or 0) + 1
                if attempts >= 8:
                    errors += 1
                    continue
                row["attempts"] = attempts
                row["error"] = str(exc)[:500]
                row["next_at"] = now + min(300, 2 ** attempts)
                kept.append(row)
                errors += 1
        _save_rows(kept)
    return {
        "ok": True,
        "flushed": flushed,
        "pending": len(kept),
        "dropped_errors": errors if flushed == 0 and errors else max(0, errors - flushed),
    }
