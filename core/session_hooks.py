"""
core/session_hooks.py
=====================
Session lifecycle hooks (ADR-063).

Events: session_start, session_end, turn_start, turn_end.
Complements tools/tool_hooks.py (tool pre/post only).
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

SessionHook = Callable[[dict[str, Any]], None]

_lock = threading.RLock()
_hooks: dict[str, list[tuple[str, SessionHook]]] = {
    "session_start": [],
    "session_end": [],
    "turn_start": [],
    "turn_end": [],
}


def reset_session_hooks_for_tests() -> None:
    with _lock:
        for k in _hooks:
            _hooks[k].clear()


def register_session_hook(event: str, name: str, fn: SessionHook) -> None:
    if event not in _hooks:
        raise ValueError(f"unknown session hook event: {event}")
    with _lock:
        _hooks[event] = [(n, f) for n, f in _hooks[event] if n != name]
        _hooks[event].append((name, fn))


def list_session_hooks() -> dict[str, list[str]]:
    with _lock:
        return {k: [n for n, _ in v] for k, v in _hooks.items()}


def emit_session_hook(event: str, payload: Optional[dict[str, Any]] = None) -> None:
    data = dict(payload or {})
    data.setdefault("event", event)
    with _lock:
        handlers = list(_hooks.get(event) or [])
    for name, fn in handlers:
        try:
            fn(data)
        except Exception:
            # Lifecycle hooks must never break the REPL.
            pass
