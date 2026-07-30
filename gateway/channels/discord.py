"""
gateway/channels/discord.py
===========================
Discord channel adapter skeleton (ADR-066).

Soft-only in this build — records messages locally. Live Discord Gateway /
REST can be enabled later behind KERROS_DISCORD_LIVE without changing the
KerrOS channel protocol.
"""

from __future__ import annotations

import os
from typing import Any

from gateway.channels.base import InboundMessage, OutboundMessage


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class DiscordAdapter:
    name = "discord"

    def __init__(self) -> None:
        self._running = False
        self._inbox: list[InboundMessage] = []
        self._outbox: list[OutboundMessage] = []

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.name,
            "enabled": _truthy(os.environ.get("KERROS_DISCORD")),
            "live": False,
            "running": self._running,
            "mode": "soft",
            "note": "live Discord transport not in this build",
        }

    def start(self) -> dict[str, Any]:
        if not _truthy(os.environ.get("KERROS_DISCORD")):
            return {"ok": False, "error": "discord disabled — set KERROS_DISCORD=1"}
        self._running = True
        return {"ok": True, "mode": "soft"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(self, text: str, *, sender: str = "user", chat_id: str = "soft") -> InboundMessage:
        msg = InboundMessage(self.name, sender, text, chat_id, {"soft": True})
        self._inbox.append(msg)
        return msg

    def poll(self) -> list[InboundMessage]:
        if not self._running:
            return []
        out = list(self._inbox)
        self._inbox.clear()
        return out

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        self._outbox.append(msg)
        return {"ok": True, "mode": "soft", "queued": len(self._outbox)}
