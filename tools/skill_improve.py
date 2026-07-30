"""
tools/skill_improve.py
======================
Skill self-improve on use (ADR-065).

When a skill is viewed, record usage and optionally append a short
"Lessons" note. Does not auto-rewrite whole skills.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from tools.claw_tools import get_workspace

STATS_NAME = "usage.json"


def _stats_path() -> Path:
    p = Path(os.path.expanduser("~/offline_ai")) / "data" / "skills_hub" / STATS_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> dict[str, Any]:
    path = _stats_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    _stats_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def record_skill_use(name: str, *, note: str = "") -> dict[str, Any]:
    key = (name or "").strip()
    if not key:
        return {"ok": False, "error": "name required"}
    data = _load()
    entry = data.get(key) if isinstance(data.get(key), dict) else {"uses": 0, "notes": []}
    entry["uses"] = int(entry.get("uses") or 0) + 1
    entry["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    note = (note or "").strip()
    if note:
        notes = list(entry.get("notes") or [])
        notes.append({"ts": entry["last_used"], "note": note[:240]})
        entry["notes"] = notes[-20:]
        _maybe_append_lesson(key, note)
    data[key] = entry
    _save(data)
    return {"ok": True, "skill": key, **entry}


def _find_skill_file(name: str) -> Optional[Path]:
    root = get_workspace() / "skills"
    if not root.is_dir():
        return None
    stem = name.replace("-", "_")
    for p in root.rglob("*.md"):
        if p.stem == stem or p.stem == name:
            return p
    return None


def _maybe_append_lesson(name: str, note: str) -> None:
    if str(os.environ.get("KERROS_SKILL_IMPROVE") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    path = _find_skill_file(name)
    if not path:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Lessons (auto)"
    line = f"- {time.strftime('%Y-%m-%d')}: {note[:200]}"
    if marker in text:
        text = text.rstrip() + "\n" + line + "\n"
    else:
        text = text.rstrip() + f"\n\n{marker}\n{line}\n"
    path.write_text(text, encoding="utf-8")


def skill_stats(name: str = "") -> dict[str, Any]:
    data = _load()
    if name:
        return {"ok": True, "skill": name, "stats": data.get(name) or {}}
    return {"ok": True, "stats": data}
