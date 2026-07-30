"""
gateway/channels/slash.py
=========================
Discord slash Soft interactions (ADR-081).

Soft handlers for /ping /status /help /resume-hint without a live Discord
Interactions endpoint. Live INTERACTION_CREATE can call the same handlers.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

from gateway.channels.base import InboundMessage

Handler = Callable[[dict[str, Any]], dict[str, Any]]

_HANDLERS: dict[str, Handler] = {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def register_slash(name: str, fn: Handler) -> None:
    _HANDLERS[name.lstrip("/").lower()] = fn


def _ping(_opts: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "type": 4, "content": "Pong — KerrOS Soft slash (ADR-081)."}


def _help(_opts: dict[str, Any]) -> dict[str, Any]:
    names = ", ".join(sorted(_HANDLERS)) or "(none)"
    return {
        "ok": True,
        "type": 4,
        "content": f"KerrOS Soft slash commands: {names}",
    }


def _status(_opts: dict[str, Any]) -> dict[str, Any]:
    from gateway.channels.registry import list_channels
    from gateway.channels.discord_gateway import get_discord_gateway

    chans = list_channels()
    gw = get_discord_gateway().status()
    body = {
        "channels": [{"name": c.get("channel"), "mode": c.get("mode")} for c in chans],
        "gateway": {"mode": gw.get("mode"), "running": gw.get("running")},
        "routing": os.environ.get("KERROS_CHANNEL_ROUTING", "1"),
    }
    return {"ok": True, "type": 4, "content": json.dumps(body)[:1800]}


def _resume_hint(opts: dict[str, Any]) -> dict[str, Any]:
    from gateway.channels.routing import session_id_for

    channel = str(opts.get("channel") or "discord")
    chat_id = str(opts.get("channel_id") or opts.get("chat_id") or "soft")
    sender = str(opts.get("user") or opts.get("sender") or "user")
    sid = session_id_for(channel, chat_id, sender)
    return {
        "ok": True,
        "type": 4,
        "content": f"Routed session: {sid} — use /resume {sid} in the REPL.",
    }


def _ensure_defaults() -> None:
    if _HANDLERS:
        return
    register_slash("ping", _ping)
    register_slash("help", _help)
    register_slash("status", _status)
    register_slash("resume-hint", _resume_hint)


def handle_slash_command(name: str, options: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    _ensure_defaults()
    key = (name or "").lstrip("/").lower()
    opts = options if isinstance(options, dict) else {}
    fn = _HANDLERS.get(key)
    if not fn:
        return {
            "ok": False,
            "type": 4,
            "content": f"Unknown Soft slash: /{key}. Try /help.",
            "error": "unknown_command",
        }
    try:
        return fn(opts)
    except Exception as exc:
        return {"ok": False, "type": 4, "content": f"slash error: {exc}", "error": str(exc)}


def soft_interaction_create(data: dict[str, Any]) -> dict[str, Any]:
    """
    Handle a Soft Discord INTERACTION_CREATE payload.

    Minimal shape: {"type": 2, "data": {"name": "ping", "options": []}, ...}
    """
    _ensure_defaults()
    data = data or {}
    cmd = ((data.get("data") or {}).get("name") if isinstance(data.get("data"), dict) else None) or ""
    opts: dict[str, Any] = {
        "channel_id": data.get("channel_id"),
        "user": ((data.get("member") or {}).get("user") or {}).get("username")
        if isinstance(data.get("member"), dict)
        else (data.get("user") or {}).get("username")
        if isinstance(data.get("user"), dict)
        else "user",
    }
    raw_opts = (data.get("data") or {}).get("options") if isinstance(data.get("data"), dict) else None
    if isinstance(raw_opts, list):
        for item in raw_opts:
            if isinstance(item, dict) and item.get("name"):
                opts[str(item["name"])] = item.get("value")
    result = handle_slash_command(str(cmd), opts)
    # Also enqueue as inbound for pump/reply demos
    try:
        from gateway.channels.discord_gateway import get_discord_gateway

        text = f"/{cmd}".strip("/")
        if text:
            get_discord_gateway()._inbox.append(
                InboundMessage(
                    channel="discord",
                    sender=str(opts.get("user") or "user"),
                    text=f"/{cmd}",
                    chat_id=str(opts.get("channel_id") or "soft"),
                    raw={"interaction": True, "slash": result},
                )
            )
    except Exception:
        pass
    return result
