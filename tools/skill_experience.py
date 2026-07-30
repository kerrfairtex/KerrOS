"""
tools/skill_experience.py
=========================
Autonomous skill creation from successful multi-tool episodes (ADR-059).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

from tools.claw_tools import get_workspace

_lock = threading.RLock()
_state = {
    "tool_calls": 0,
    "tools": [],
    "succeeded": True,
    "task_hint": "",
}


def reset_episode() -> None:
    with _lock:
        _state["tool_calls"] = 0
        _state["tools"] = []
        _state["succeeded"] = True
        _state["task_hint"] = ""


def record_tool_call(tool: str, result: Any) -> None:
    with _lock:
        _state["tool_calls"] += 1
        _state["tools"].append(str(tool))
        text = str(result or "")
        if text.startswith("[SCOPE GATE]") or text.startswith("[TOOL HOOK") or text.startswith("[Error"):
            _state["succeeded"] = False


def set_task_hint(text: str) -> None:
    with _lock:
        _state["task_hint"] = (text or "")[:200]


def episode_snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def maybe_create_skill(*, min_tools: int = 5) -> Optional[str]:
    """If episode succeeded with enough tools, write a reusable skill markdown."""
    snap = episode_snapshot()
    if snap["tool_calls"] < min_tools or not snap["succeeded"]:
        return None
    tools = snap["tools"]
    hint = snap["task_hint"] or "multi-step task"
    slug = re.sub(r"[^a-z0-9_]+", "_", hint.lower())[:40].strip("_") or "episode"
    name = f"auto_{slug}_{int(time.time()) % 100000}"
    category = "learned"
    root = get_workspace() / "skills" / category
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.md"
    uniq = []
    for t in tools:
        if t not in uniq:
            uniq.append(t)
    from tools.skill_provenance import (
        BACKGROUND_REVIEW,
        get_current_write_origin,
        reset_current_write_origin,
        set_current_write_origin,
    )

    token = set_current_write_origin(BACKGROUND_REVIEW)
    try:
        body = "\n".join(
            [
                f"# Learned: {hint}",
                "",
                f"Auto-created after {snap['tool_calls']} successful tool calls.",
                "",
                "## Approach",
                f"Tools used in order: {', '.join(tools)}",
                "",
                "## Reuse",
                "- Prefer this sequence when facing a similar fixed multi-step task.",
                f"- Unique tools: {', '.join(uniq)}",
                "",
                f"<!-- kerros:pinned=false created={time.strftime('%Y-%m-%d')} origin={get_current_write_origin()} -->",
                "",
            ]
        )
        path.write_text(body, encoding="utf-8")
    finally:
        reset_current_write_origin(token)
    reset_episode()
    return str(path)


def curate_skills(*, unused_days: int = 90, archive: bool = True) -> dict[str, Any]:
    """Dedupe by title; optionally archive very old unpinned skills."""
    root = get_workspace() / "skills"
    if not root.is_dir():
        return {"ok": True, "archived": [], "dupes": []}
    by_title: dict[str, list[Path]] = {}
    archived: list[str] = []
    dupes: list[str] = []
    now = time.time()
    for path in root.rglob("*.md"):
        if "tool_catalog" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        pinned = "kerros:pinned=true" in text
        title = path.stem
        for line in text.splitlines():
            if line.startswith("#"):
                title = line.lstrip("#").strip().lower()
                break
        by_title.setdefault(title, []).append(path)
        age_days = (now - path.stat().st_mtime) / 86400.0
        if archive and (not pinned) and age_days >= unused_days and title.startswith("learned"):
            dest_dir = root / "_archive"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / path.name
            path.rename(dest)
            archived.append(str(dest))
    for title, paths in by_title.items():
        if len(paths) <= 1:
            continue
        # Keep newest; archive older unpinned duplicates.
        paths_sorted = sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)
        for extra in paths_sorted[1:]:
            try:
                text = extra.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "kerros:pinned=true" in text:
                continue
            dest_dir = root / "_archive"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / extra.name
            if extra.exists():
                extra.rename(dest)
                dupes.append(str(dest))
    return {"ok": True, "archived": archived, "dupes": dupes}
