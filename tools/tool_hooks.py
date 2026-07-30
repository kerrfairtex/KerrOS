"""
tools/tool_hooks.py
===================
Pre/post tool-call hooks (ADR-056).

Default: ``scope_gate.check`` is registered as the first pre-hook.
Hooks must not print secrets. Pre-hook exceptions deny the call.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

PreHook = Callable[[str, Any], tuple[bool, str]]
PostHook = Callable[[str, Any, Any], None]

_lock = threading.RLock()
_pre: list[tuple[str, PreHook]] = []
_post: list[tuple[str, PostHook]] = []
_bootstrapped = False


def reset_hooks_for_tests() -> None:
    """Clear hooks and re-bootstrap defaults (unit tests only)."""
    global _bootstrapped
    with _lock:
        _pre.clear()
        _post.clear()
        _bootstrapped = False
    ensure_default_hooks()


def register_pre_tool_call(name: str, fn: PreHook, *, prepend: bool = False) -> None:
    ensure_default_hooks()
    with _lock:
        if prepend:
            _pre.insert(0, (name, fn))
        else:
            _pre.append((name, fn))


def register_post_tool_call(name: str, fn: PostHook) -> None:
    ensure_default_hooks()
    with _lock:
        _post.append((name, fn))


def _scope_gate_pre(tool: str, args: Any) -> tuple[bool, str]:
    from tools.scope_gate import check as _scope_check

    return _scope_check(tool, args)


def ensure_default_hooks() -> None:
    global _bootstrapped
    with _lock:
        if _bootstrapped:
            return
        _pre.append(("scope_gate", _scope_gate_pre))
        _bootstrapped = True


def run_pre_tool_call(tool: str, args: Any) -> tuple[bool, str, str]:
    """Return (allowed, reason, hook_name). First denial wins."""
    ensure_default_hooks()
    with _lock:
        hooks = list(_pre)
    for name, fn in hooks:
        try:
            ok, reason = fn(tool, args)
        except Exception as exc:
            return False, f"pre_hook:{name}: {exc}", name
        if not ok:
            return False, reason or f"denied by {name}", name
    return True, "ok", ""


def run_post_tool_call(tool: str, args: Any, result: Any) -> None:
    ensure_default_hooks()
    with _lock:
        hooks = list(_post)
    for name, fn in hooks:
        try:
            fn(tool, args, result)
        except Exception:
            # Post hooks never fail the tool result.
            continue


def list_hooks() -> dict[str, list[str]]:
    ensure_default_hooks()
    with _lock:
        return {
            "pre": [n for n, _ in _pre],
            "post": [n for n, _ in _post],
        }
