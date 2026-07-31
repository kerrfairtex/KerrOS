"""
gateway/channels/export.py
==========================
Soft SIEM / trace export (ADR-089).

Exports channel_trace JSONL to a Soft CEF-ish or JSON bundle for operators.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def export_trace(
    *,
    format: str = "json",
    limit: int = 200,
    path: Optional[str] = None,
) -> dict[str, Any]:
    from gateway.channels.trace import read_trace

    rows = read_trace(limit=limit)
    fmt = (format or "json").strip().lower()
    ext = "txt" if fmt == "cef" else "json"
    out_path = Path(
        os.path.expanduser(
            path
            or str(
                Path(os.path.expanduser("~/offline_ai"))
                / "data"
                / f"channel_trace_export_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"
            )
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "cef":
        lines = []
        for r in rows:
            det = r.get("detail") or {}
            msg = json.dumps(det, ensure_ascii=False)[:200] if det else "-"
            lines.append(
                f"CEF:0|KerrOS|channel-trace|1.0|{r.get('kind')}|{r.get('kind')}|1|"
                f"rt={r.get('ts')} msg={msg}"
            )
        out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    else:
        payload = {
            "ok": True,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "count": len(rows),
            "events": rows,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "format": fmt,
        "count": len(rows),
        "path": str(out_path),
    }
