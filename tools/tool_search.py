"""
tools/tool_search.py
====================
Progressive tool disclosure (ADR-062).

When enabled, large tool catalogs can be hidden behind bridge tools:
  tool_search / tool_describe / tool_exec_by_name
Core always-on tools stay eager.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

# Tools that must never be deferred (KerrOS core surface).
ALWAYS_EAGER = frozenset({
    "calc", "sysinfo", "file_read", "bash",
    "skills_list", "skill_view", "skill_manage",
    "search_past_sessions", "profile_memory",
    "tool_search", "tool_describe", "tool_exec_by_name",
    "delegate_task", "execute_pipeline",
})

BRIDGE_NAMES = frozenset({"tool_search", "tool_describe", "tool_exec_by_name"})


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on", "auto")


def is_tool_search_enabled(cfg: Optional[dict] = None) -> bool:
    env = os.environ.get("KERROS_TOOL_SEARCH")
    if env is not None:
        return _truthy(env)
    block = (cfg or {}).get("tool_search") if isinstance((cfg or {}).get("tool_search"), dict) else {}
    return _truthy(block.get("enabled", False))


def _catalog() -> list[dict[str, str]]:
    """Build name+description list from router dispatch + registry if present."""
    items: list[dict[str, str]] = []
    try:
        from tools.registry import list_tools

        for spec in list_tools() or []:
            fn = (spec.get("function") or {}) if isinstance(spec, dict) else {}
            name = str(fn.get("name") or "")
            if not name:
                continue
            items.append({
                "name": name,
                "description": str(fn.get("description") or "")[:200],
            })
    except Exception:
        pass
    # Fallback: known router tool names
    if not items:
        try:
            from kernel import router as R

            # probe detect surface via known names in module docs — use dispatch keys if exposed
            for name in sorted(ALWAYS_EAGER):
                items.append({"name": name, "description": ""})
        except Exception:
            pass
    return items


def search_tools(query: str, limit: int = 8) -> dict[str, Any]:
    q = (query or "").strip().lower()
    limit = max(1, min(int(limit or 8), 30))
    cat = _catalog()
    if not q:
        return {"ok": True, "results": cat[:limit], "total": len(cat)}
    scored: list[tuple[int, dict[str, str]]] = []
    tokens = [t for t in re.split(r"\W+", q) if t]
    for item in cat:
        blob = f"{item['name']} {item.get('description','')}".lower()
        score = sum(3 if t in item["name"].lower() else 1 for t in tokens if t in blob)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    return {"ok": True, "results": [i for _, i in scored[:limit]], "total": len(scored)}


def describe_tool(name: str) -> dict[str, Any]:
    name = (name or "").strip()
    for item in _catalog():
        if item["name"] == name:
            return {"ok": True, "tool": item}
    return {"ok": False, "error": f"unknown tool: {name}"}


def filter_eager_tools(tool_defs: list[dict], *, cfg: Optional[dict] = None) -> list[dict]:
    """If tool search enabled and catalog large, keep ALWAYS_EAGER + bridges only."""
    if not is_tool_search_enabled(cfg):
        return tool_defs
    if len(tool_defs) < 25:
        return tool_defs
    out = []
    for spec in tool_defs:
        fn = (spec.get("function") or {}) if isinstance(spec, dict) else {}
        name = str(fn.get("name") or "")
        if name in ALWAYS_EAGER or name in BRIDGE_NAMES:
            out.append(spec)
    return out
