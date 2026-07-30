"""
memory/nudges.py
================
Periodic memory / skill persistence nudges (ADR-065).

After N turns without a profile_memory write, return a short system
reminder the REPL can inject. Default-off unless KERROS_MEMORY_NUDGES=1.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

_lock = threading.RLock()
_state = {
    "turns": 0,
    "turns_since_memory": 0,
    "turns_since_skill": 0,
}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    return _truthy(os.environ.get("KERROS_MEMORY_NUDGES"))


def interval(kind: str = "memory") -> int:
    if kind == "skill":
        return int(os.environ.get("KERROS_SKILL_NUDGE_EVERY") or 12)
    return int(os.environ.get("KERROS_MEMORY_NUDGE_EVERY") or 8)


def note_turn() -> None:
    with _lock:
        _state["turns"] += 1
        _state["turns_since_memory"] += 1
        _state["turns_since_skill"] += 1


def note_memory_write() -> None:
    with _lock:
        _state["turns_since_memory"] = 0


def note_skill_write() -> None:
    with _lock:
        _state["turns_since_skill"] = 0


def pending_nudges() -> list[str]:
    if not is_enabled():
        return []
    out: list[str] = []
    with _lock:
        if _state["turns_since_memory"] >= interval("memory"):
            out.append(
                "[nudge] Consider saving durable facts with "
                "`profile memory add :: user|memory :: <text>`."
            )
            _state["turns_since_memory"] = 0
        if _state["turns_since_skill"] >= interval("skill"):
            out.append(
                "[nudge] If this procedure is reusable, save a skill via "
                "`skill_manage` or `skills hub install`."
            )
            _state["turns_since_skill"] = 0
    return out


def reset_for_tests() -> None:
    with _lock:
        _state["turns"] = 0
        _state["turns_since_memory"] = 0
        _state["turns_since_skill"] = 0
