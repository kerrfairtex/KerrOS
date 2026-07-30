"""
gateway/channels/discord.py
===========================
Discord channel adapter (ADR-066 / ADR-069).

Default Soft/Fake — no network. Enable live Bot REST with:
  KERROS_DISCORD=1
  KERROS_DISCORD_LIVE=1
  KERROS_DISCORD_TOKEN=<bot token>
  KERROS_DISCORD_CHANNEL=<default channel id>   # optional; send may override

Live path uses HTTPS REST (channel messages). Soft path records inbox/outbox
in memory for CI and local demos. Gateway websocket Soft/live is ADR-075
(`gateway/channels/discord_gateway.py`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from gateway.channels.base import InboundMessage, OutboundMessage

API_BASE = "https://discord.com/api/v10"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class DiscordAdapter:
    name = "discord"

    def __init__(self) -> None:
        self._running = False
        self._last_message_id: Optional[str] = None
        self._soft_inbox: list[InboundMessage] = []
        self._soft_outbox: list[OutboundMessage] = []

    def _enabled(self) -> bool:
        return _truthy(os.environ.get("KERROS_DISCORD"))

    def _live(self) -> bool:
        return _truthy(os.environ.get("KERROS_DISCORD_LIVE")) and bool(
            os.environ.get("KERROS_DISCORD_TOKEN")
        )

    def _token(self) -> str:
        return (os.environ.get("KERROS_DISCORD_TOKEN") or "").strip()

    def _default_channel(self) -> str:
        return (os.environ.get("KERROS_DISCORD_CHANNEL") or "").strip()

    def _api(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict] = None,
        query: str = "",
    ) -> dict[str, Any]:
        token = self._token()
        if not token:
            return {"ok": False, "error": "missing KERROS_DISCORD_TOKEN"}
        url = f"{API_BASE}{path}"
        if query:
            url = f"{url}?{query}"
        data = None
        headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": "KerrOS-DiscordAdapter (local; ADR-069)",
            "Content-Type": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw.strip():
                    return {"ok": True, "result": None}
                parsed = json.loads(raw)
            if isinstance(parsed, list):
                return {"ok": True, "result": parsed}
            if isinstance(parsed, dict):
                # Discord errors look like {"message": "...", "code": N}
                if "code" in parsed and "message" in parsed and "id" not in parsed:
                    return {
                        "ok": False,
                        "error": parsed.get("message"),
                        "code": parsed.get("code"),
                    }
                return {"ok": True, "result": parsed}
            return {"ok": False, "error": "bad response"}
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            return {"ok": False, "error": detail or str(exc), "status": exc.code}
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
            "default_channel": self._default_channel() or None,
            "soft_inbox": len(self._soft_inbox),
            "soft_outbox": len(self._soft_outbox),
            "note": None
            if self._live()
            else "live Discord REST behind KERROS_DISCORD_LIVE=1 (no Gateway websocket)",
        }

    def start(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "error": "discord disabled — set KERROS_DISCORD=1"}
        self._running = True
        if self._live():
            me = self._api("GET", "/users/@me")
            return {
                "ok": bool(me.get("ok")),
                "mode": "live",
                "me": me.get("result"),
                "error": me.get("error"),
            }
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
            chat_id=chat_id or self._default_channel() or "soft",
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
        channel_id = self._default_channel()
        if not channel_id:
            return []
        query = "limit=25"
        if self._last_message_id:
            query += f"&after={self._last_message_id}"
        res = self._api("GET", f"/channels/{channel_id}/messages", query=query)
        if not res.get("ok"):
            return []
        rows = res.get("result") or []
        if not isinstance(rows, list):
            return []
        # Discord returns newest-first; process oldest-first
        rows = list(reversed(rows))
        messages: list[InboundMessage] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            mid = str(row.get("id") or "")
            if mid:
                self._last_message_id = mid
            # Skip bot's own messages when author.bot
            author = row.get("author") or {}
            if author.get("bot"):
                continue
            text = str(row.get("content") or "").strip()
            if not text:
                continue
            messages.append(
                InboundMessage(
                    channel=self.name,
                    sender=str(author.get("username") or author.get("id") or "unknown"),
                    text=text[:4000],
                    chat_id=str(row.get("channel_id") or channel_id),
                    raw=row,
                )
            )
        return messages

    def send(self, msg: OutboundMessage) -> dict[str, Any]:
        if not self._live():
            self._soft_outbox.append(msg)
            return {"ok": True, "mode": "soft", "queued": len(self._soft_outbox)}
        channel_id = (msg.chat_id or self._default_channel() or "").strip()
        if not channel_id:
            return {
                "ok": False,
                "mode": "live",
                "error": "missing chat_id / KERROS_DISCORD_CHANNEL",
            }
        res = self._api(
            "POST",
            f"/channels/{channel_id}/messages",
            body={"content": (msg.text or "")[:2000]},
        )
        return {
            "ok": bool(res.get("ok")),
            "mode": "live",
            "result": res.get("result"),
            "error": res.get("error"),
        }
