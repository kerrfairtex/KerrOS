"""
gateway/channels/whatsapp.py
============================
WhatsApp channel adapter (ADR-070 / ADR-076).

Default Soft. Live Cloud API behind:
  KERROS_WHATSAPP=1
  KERROS_WHATSAPP_LIVE=1
  KERROS_WHATSAPP_TOKEN=<access token>
  KERROS_WHATSAPP_PHONE_ID=<phone number id>
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from gateway.channels.base import InboundMessage, OutboundMessage

GRAPH_BASE = "https://graph.facebook.com/v19.0"


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

    def _live(self) -> bool:
        return (
            _truthy(os.environ.get("KERROS_WHATSAPP_LIVE"))
            and bool(os.environ.get("KERROS_WHATSAPP_TOKEN"))
            and bool(os.environ.get("KERROS_WHATSAPP_PHONE_ID"))
        )

    def _token(self) -> str:
        return (os.environ.get("KERROS_WHATSAPP_TOKEN") or "").strip()

    def _phone_id(self) -> str:
        return (os.environ.get("KERROS_WHATSAPP_PHONE_ID") or "").strip()

    def _api(self, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        token = self._token()
        if not token:
            return {"ok": False, "error": "missing KERROS_WHATSAPP_TOKEN"}
        url = f"{GRAPH_BASE}{path}"
        data = json.dumps(body or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": "KerrOS-WhatsAppAdapter (ADR-076)",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw.strip() else {}
            if isinstance(parsed, dict) and parsed.get("error"):
                err = parsed.get("error") or {}
                return {
                    "ok": False,
                    "error": err.get("message") if isinstance(err, dict) else str(err),
                }
            return {"ok": True, "result": parsed}
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            return {"ok": False, "error": detail or str(exc)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.name,
            "enabled": self._enabled(),
            "live": self._live(),
            "running": self._running,
            "mode": "live" if self._live() else "soft",
            "soft_inbox": len(self._soft_inbox),
            "soft_outbox": len(self._soft_outbox),
            "note": None
            if self._live()
            else "live Cloud API behind KERROS_WHATSAPP_LIVE=1 + token/phone id",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "whatsapp disabled — set KERROS_WHATSAPP=1"}
        self._running = True
        if self._live():
            return {"ok": True, "mode": "live", "phone_id": self._phone_id()}
        return {"ok": True, "mode": "soft", "note": "inject via soft_push or soft_push_webhook"}

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
        # Live inbound is webhook-driven; Soft inbox covers CI + local inject
        out = list(self._soft_inbox)
        self._soft_inbox.clear()
        return out

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        if not self._live():
            self._soft_outbox.append(msg)
            return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
        to = (msg.chat_id or "").strip()
        if not to:
            return {"ok": False, "mode": "live", "error": "missing chat_id (E.164)"}
        res = self._api(
            f"/{self._phone_id()}/messages",
            {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": (msg.text or "")[:4096]},
            },
        )
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "result": res.get("result"),
            "error": res.get("error"),
        }
