"""
gateway/channels/signal.py
==========================
Signal channel adapter Soft skeleton (ADR-071).

Soft-only — local inbox/outbox for CI and demos. A later ADR can bridge a
local signal-cli daemon behind KERROS_SIGNAL_LIVE without changing the
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


class SignalAdapter:
    name = "signal"

    def __init__(self) -> None:
        self._running = False
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_SIGNAL"))

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.name,
            "enabled": self._enabled(),
            "live": False,
            "running": self._running,
            "mode": "soft",
            "soft_inbox": len(self._soft_inbox),
            "soft_outbox": len(self._soft_outbox),
            "note": "live signal-cli bridge not in this build",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "signal disabled — set KERROS_SIGNAL=1"}
        self._running = True
        return {"ok": True, "mode": "soft", "note": "inject via soft_push or gateway webhook"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(
        self, text: str, *, sender: str = "user", chat_id: str = "soft"
    ) -> InboundMessage:
        msg = InboundMessage(
            channel=self.name,
            sender=sender,
            text=text,
            chat_id=chat_id,
            raw={"soft": True},
        )
        self._soft_inbox.append(msg)
        return msg

    def poll(self) -> list[InboundMessage]:
        if not self._running:
            return []
        out = list(self._soft_inbox)
        self._soft_inbox.clear()
        return out

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        self._soft_outbox.append(msg)
        return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
