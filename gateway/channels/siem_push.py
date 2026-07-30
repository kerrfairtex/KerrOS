"""
gateway/channels/siem_push.py
=============================
Soft live SIEM HTTP push (ADR-094).

Posts recent trace events as JSON or CEF lines to KERROS_SIEM_URL when
KERROS_SIEM_PUSH=1. Soft-plans when disabled.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def push_enabled() -> bool:
    return _truthy(os.environ.get("KERROS_SIEM_PUSH")) and bool(
        (os.environ.get("KERROS_SIEM_URL") or "").strip()
    )


def push_trace(*, format: str = "json", limit: int = 50) -> dict[str, Any]:
    from gateway.channels.export import export_trace
    from gateway.channels.trace import read_trace

    rows = read_trace(limit=limit)
    fmt = (format or "json").strip().lower()
    url = (os.environ.get("KERROS_SIEM_URL") or "").strip()
    if not push_enabled():
        return {
            "ok": True,
            "soft": True,
            "count": len(rows),
            "note": "set KERROS_SIEM_PUSH=1 and KERROS_SIEM_URL to live-push",
        }
    if fmt == "cef":
        lines = []
        for r in rows:
            det = r.get("detail") or {}
            msg = json.dumps(det, ensure_ascii=False)[:200] if det else "-"
            lines.append(
                f"CEF:0|KerrOS|channel-trace|1.0|{r.get('kind')}|{r.get('kind')}|1|"
                f"rt={r.get('ts')} msg={msg}"
            )
        body = ("\n".join(lines) + "\n").encode("utf-8")
        content_type = "text/plain"
    else:
        body = json.dumps({"ok": True, "events": rows, "source": "kerros"}).encode("utf-8")
        content_type = "application/json"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "User-Agent": "KerrOS-SIEMPush (ADR-094)",
        },
    )
    token = (os.environ.get("KERROS_SIEM_TOKEN") or "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return {
            "ok": True,
            "soft": False,
            "count": len(rows),
            "format": fmt,
            "url": url,
            "response": raw[:500],
        }
    except Exception as exc:
        return {"ok": False, "soft": False, "error": str(exc), "count": len(rows)}
