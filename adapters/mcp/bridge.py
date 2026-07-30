"""
adapters/mcp/bridge.py
======================
Soft MCP tool bridge (ADR-062).

Default-off. When KERROS_MCP=1 and servers are listed in config mcp_servers,
exposes discovered tool names for progressive disclosure. Live JSON-RPC is
optional — without a running server the bridge stays Fake/list-only so CI
never depends on network MCP.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

_discovered: list[dict[str, Any]] = []


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def is_mcp_enabled(cfg: Optional[dict] = None) -> bool:
    env = os.environ.get("KERROS_MCP")
    if env is not None:
        return _truthy(env)
    block = (cfg or {}).get("mcp") if isinstance((cfg or {}).get("mcp"), dict) else {}
    return _truthy(block.get("enabled", False))


def list_mcp_servers(cfg: Optional[dict] = None) -> list[dict[str, Any]]:
    data = cfg or {}
    try:
        from core.config import cfg as _cfg
        data = data or _cfg()
    except Exception:
        pass
    block = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    servers = block.get("servers") or []
    return servers if isinstance(servers, list) else []


def discover_tools(cfg: Optional[dict] = None) -> dict[str, Any]:
    """Fake discovery: return configured tool stubs without live RPC."""
    global _discovered
    if not is_mcp_enabled(cfg):
        return {"ok": False, "error": "MCP disabled — set KERROS_MCP=1", "tools": []}
    tools = []
    for srv in list_mcp_servers(cfg):
        if not isinstance(srv, dict):
            continue
        name = str(srv.get("name") or "server")
        for t in srv.get("tools") or []:
            if isinstance(t, str):
                tools.append({"server": name, "name": t, "description": f"MCP:{name}/{t}"})
            elif isinstance(t, dict):
                tools.append({
                    "server": name,
                    "name": str(t.get("name") or ""),
                    "description": str(t.get("description") or ""),
                })
    _discovered = tools
    return {"ok": True, "tools": tools, "mode": "soft"}


def call_mcp_tool(server: str, tool: str, arguments: Optional[dict] = None) -> dict[str, Any]:
    if not is_mcp_enabled():
        return {"ok": False, "error": "MCP disabled"}
    allow_live = _truthy(os.environ.get("KERROS_MCP_LIVE"))
    if not allow_live:
        return {
            "ok": False,
            "error": "live MCP RPC disabled (soft mode); set KERROS_MCP_LIVE=1 to enable",
            "server": server,
            "tool": tool,
            "arguments": arguments or {},
        }
    # Live path intentionally minimal — operators wire transport later.
    return {"ok": False, "error": "live MCP transport not configured in this build"}
