"""
gateway/channels/whatsapp.py
============================
WhatsApp channel adapter Soft skeleton (ADR-070).

Soft-only in this build — records inbox/outbox locally and accepts
webhook-shaped soft payloads. Live Cloud API can be enabled later behind
KERROS_WHATSAPP_LIVE without changing the KerrOS channel protocol.
"""

from __future__ import annotations

import os
from typing import Any

from gateway.channels.base import InboundMessage, OutboundMessage


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class WhatsAppAdapter:
    name = "whatsapp"

    def __init__(self) -> None:
        self._running = False
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_WHATSAPP"))

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
            "note": "live WhatsApp Cloud API not in this build",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "whatsapp disabled — set KERROS_WHATSAPP=1"}
        self._running = True
        return {"ok": True, "mode": "soft", "note": "inject via soft_push or gateway webhook"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(
        self,
        text: str,
        *,
        sender: str = "user",
        chat_id: str = "soft",
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

    def soft_push_webhook(self, payload: dict[str, Any]) -> list[InboundMessage]:
        """
        Accept a Cloud-API-shaped Soft webhook payload and enqueue texts.

        Expected minimal shape:
          {"entry":[{"changes":[{"value":{"messages":[{"from":"…","text":{"body":"…"}}]}}]}]}
        """
        out: list[InboundMessage] = []
        if not isinstance(payload, dict):
            return out
        for entry in payload.get("entry") or []:
            if not isinstance(entry, dict):
                continue
            for change in entry.get("changes") or []:
                if not isinstance(change, dict):
                    continue
                value = change.get("value") or {}
                if not isinstance(value, dict):
                    continue
                for m in value.get("messages") or []:
                    if not isinstance(m, dict):
                        continue
                    body = ""
                    text = m.get("text") or {}
                    if isinstance(text, dict):
                        body = str(text.get("body") or "").strip()
                    if not body:
                        continue
                    sender = str(m.get("from") or "unknown")
                    msg = InboundMessage(
                        channel=self.name,
                        sender=sender,
                        text=body[:4000],
                        chat_id=sender,
                        raw={"soft": True, "message": m},
                    )
                    self._soft_inbox.append(msg)
                    out.append(msg)
        return out

    def poll(self) -> list[InboundMessage]:
        if not self._running:
            return []
        out = list(self._soft_inbox)
        self._soft_inbox.clear()
        return out

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        self._soft_outbox.append(msg)
        return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
