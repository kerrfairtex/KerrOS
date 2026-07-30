"""
gateway/channels/telegram.py
============================
Telegram channel adapter (ADR-066).

Default Soft/Fake — no network. Enable live Bot API with:
  KERROS_TELEGRAM=1
  KERROS_TELEGRAM_LIVE=1
  KERROS_TELEGRAM_TOKEN=<bot token>

Live path uses HTTPS getUpdates / sendMessage. Soft path records inbox/outbox
in memory for CI and local demos.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from gateway.channels.base import InboundMessage, OutboundMessage


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class TelegramAdapter:
    name = "telegram"

    def __init__(self) -> None:
        self._running = False
        self._offset = 0
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []
        self._soft_edits: list[dict[str, Any]] = []

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_TELEGRAM", os.environ.get("KERROS_GATEWAY")))

    def _live(self) -> bool:
        return _truthy(os.environ.get("KERROS_TELEGRAM_LIVE")) and bool(
            os.environ.get("KERROS_TELEGRAM_TOKEN")
        )

    def _token(self) -> str:
        return (os.environ.get("KERROS_TELEGRAM_TOKEN") or "").strip()

    def _api(self, method: str, params: Optional[dict] = None) -> dict[str, Any]:
        token = self._token()
        if not token:
            return {"ok": False, "error": "missing KERROS_TELEGRAM_TOKEN"}
        url = f"https://api.telegram.org/bot{token}/{method}"
        data = urllib.parse.urlencode(params or {}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8", errors="replace"))
            return body if isinstance(body, dict) else {"ok": False, "error": "bad response"}
        except urllib.error.URLError as exc:
            return {"ok": False, "error": str(exc)}
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
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "telegram disabled — set KERROS_TELEGRAM=1"}
        self._running = True
        if self._live():
            me = self._api("getMe")
            return {"ok": bool(me.get("ok")), "mode": "live", "me": me.get("result"), "error": me.get("error") or me.get("description")}
        return {"ok": True, "mode": "soft", "note": "inject via soft_push or gateway webhook"}

    def stop(self) -> dict[str, Any]:
        self._running = False
        return {"ok": True, "stopped": True}

    def soft_push(self, text: str, *, sender: str = "user", chat_id: str = "soft") -> InboundMessage:
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
        if not self._live():
            out = list(self._soft_inbox)
            self._soft_inbox.clear()
            return out
        res = self._api("getUpdates", {"offset": self._offset, "timeout": 0})
        if not res.get("ok"):
            return []
        messages: list[InboundMessage] = []
        for upd in res.get("result") or []:
            if not isinstance(upd, dict):
                continue
            self._offset = max(self._offset, int(upd.get("update_id") or 0) + 1)
            msg = upd.get("message") or upd.get("edited_message") or {}
            text = str(msg.get("text") or "").strip()
            if not text:
                continue
            chat = msg.get("chat") or {}
            from_u = msg.get("from") or {}
            messages.append(
                InboundMessage(
                    channel=self.name,
                    sender=str(from_u.get("username") or from_u.get("id") or "unknown"),
                    text=text[:4000],
                    chat_id=str(chat.get("id") or ""),
                    raw=upd,
                )
            )
        return messages

    def soft_edit(self, message_id: str, text: str, *, chat_id: str = "soft") -> dict[str, Any]:
        """ADR-102 Soft progressive edit record (and live editMessageText when live)."""
        entry = {
            "message_id": message_id,
            "chat_id": chat_id,
            "text": (text or "")[:4000],
        }
        self._soft_edits.append(entry)
        if not self._live():
            return {"ok": True, "mode": "soft", "edits": len(self._soft_edits)}
        res = self._api(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": (text or "")[:4000]},
        )
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "result": res.get("result"),
            "error": res.get("description") or res.get("error"),
        }

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        if not self._live():
            self._soft_outbox.append(msg)
            return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
        res = self._api(
            "sendMessage",
            {"chat_id": msg.chat_id, "text": msg.text[:4000]},
        )
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "result": res.get("result"),
            "error": res.get("description") or res.get("error"),
        }
