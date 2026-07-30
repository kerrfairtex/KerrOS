"""
adapters/mcp/bridge.py
======================
Soft MCP tool bridge (ADR-062/063).

Default-off. When KERROS_MCP=1 and servers are listed in config,
exposes discovered tool names. Live JSON-RPC over HTTP is optional
behind KERROS_MCP_LIVE=1 (stdio transport still Soft/stub).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
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
    """Soft discovery from config stubs; optionally probe HTTP list endpoints."""
    global _discovered
    if not is_mcp_enabled(cfg):
        return {"ok": False, "error": "MCP disabled — set KERROS_MCP=1", "tools": []}
    tools: list[dict[str, Any]] = []
    mode = "soft"
    for srv in list_mcp_servers(cfg):
        if not isinstance(srv, dict):
            continue
        name = str(srv.get("name") or "server")
        for t in srv.get("tools") or []:
            if isinstance(t, str):
                tools.append({"server": name, "name": t, "description": f"MCP:{name}/{t}"})
            elif isinstance(t, dict):
                tools.append(
                    {
                        "server": name,
                        "name": str(t.get("name") or ""),
                        "description": str(t.get("description") or ""),
                    }
                )
        # Optional live HTTP tools/list when enabled
        if _truthy(os.environ.get("KERROS_MCP_LIVE")) and srv.get("url"):
            live = _http_tools_list(str(srv["url"]), name)
            if live.get("ok"):
                mode = "http"
                tools.extend(live.get("tools") or [])
    _discovered = tools
    return {"ok": True, "tools": tools, "mode": mode}


def _http_json_rpc(url: str, method: str, params: Optional[dict] = None, *, timeout: float = 5.0) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if isinstance(data, dict) and data.get("error"):
            return {"ok": False, "error": str(data["error"])}
        return {"ok": True, "result": data.get("result") if isinstance(data, dict) else data}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"http error: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _http_tools_list(url: str, server: str) -> dict[str, Any]:
    out = _http_json_rpc(url, "tools/list")
    if not out.get("ok"):
        return out
    result = out.get("result") or {}
    tools_raw = result.get("tools") if isinstance(result, dict) else []
    tools = []
    for t in tools_raw or []:
        if not isinstance(t, dict):
            continue
        tools.append(
            {
                "server": server,
                "name": str(t.get("name") or ""),
                "description": str(t.get("description") or "")[:200],
            }
        )
    return {"ok": True, "tools": tools}


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
    # Find server URL from config
    url = None
    for srv in list_mcp_servers():
        if isinstance(srv, dict) and str(srv.get("name") or "") == server:
            url = srv.get("url")
            break
    if not url:
        return {"ok": False, "error": f"no url configured for MCP server '{server}' (stdio not in this build)"}
    return _http_json_rpc(
        str(url),
        "tools/call",
        {"name": tool, "arguments": arguments or {}},
    )
