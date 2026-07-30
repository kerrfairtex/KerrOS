"""
gateway/channels/registry.py
============================
Channel adapter registry + pump into webhook inbox (ADR-066).
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from gateway.channels.base import ChannelAdapter, InboundMessage, OutboundMessage

_lock = threading.RLock()
_adapters: dict[str, Any] = {}
_bootstrapped = False


def _bootstrap() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    from gateway.channels.discord import DiscordAdapter
    from gateway.channels.telegram import TelegramAdapter

    _adapters["telegram"] = TelegramAdapter()
    _adapters["discord"] = DiscordAdapter()
    _bootstrapped = True


def register_channel(name: str, adapter: Any) -> None:
    with _lock:
        _bootstrap()
        _adapters[name] = adapter


def get_adapter(name: str) -> Optional[Any]:
    with _lock:
        _bootstrap()
        return _adapters.get(name)


def list_channels() -> list[dict[str, Any]]:
    with _lock:
        _bootstrap()
        return [a.status() for a in _adapters.values()]


def start_channel(name: str) -> dict[str, Any]:
    ad = get_adapter(name)
    if not ad:
        return {"ok": False, "error": f"unknown channel: {name}"}
    return ad.start()


def stop_channel(name: str) -> dict[str, Any]:
    ad = get_adapter(name)
    if not ad:
        return {"ok": False, "error": f"unknown channel: {name}"}
    return ad.stop()


def poll_all() -> list[InboundMessage]:
    with _lock:
        _bootstrap()
        msgs: list[InboundMessage] = []
        for ad in _adapters.values():
            try:
                msgs.extend(ad.poll() or [])
            except Exception:
                pass
        return msgs


def pump_to_webhook_inbox() -> dict[str, Any]:
    """Pull channel polls into the HTTP gateway inbox for unified handling."""
    from gateway import webhook as gw

    pulled = poll_all()
    for m in pulled:
        # reuse webhook inbox store
        with gw._lock:
            gw._inbox.append(
                {
                    "channel": m.channel,
                    "sender": m.sender,
                    "text": m.text,
                    "chat_id": m.chat_id,
                }
            )
    return {"ok": True, "pulled": len(pulled)}


def send_channel(channel: str, chat_id: str, text: str) -> dict[str, Any]:
    ad = get_adapter(channel)
    if not ad:
        return {"ok": False, "error": f"unknown channel: {channel}"}
    return ad.send(OutboundMessage(channel=channel, chat_id=chat_id, text=text))


def channels_cmd(action: str, raw: str = "") -> str:
    import json

    action = (action or "list").strip().lower()
    parts = [p.strip() for p in (raw or "").split() if p.strip()]
    if action in ("list", "status"):
        return json.dumps({"ok": True, "channels": list_channels()}, indent=2)
    if action == "start" and parts:
        return json.dumps(start_channel(parts[0]), indent=2)
    if action == "stop" and parts:
        return json.dumps(stop_channel(parts[0]), indent=2)
    if action == "pump":
        return json.dumps(pump_to_webhook_inbox(), indent=2)
    if action == "send" and len(parts) >= 3:
        channel, chat_id = parts[0], parts[1]
        text = " ".join(parts[2:])
        return json.dumps(send_channel(channel, chat_id, text), indent=2)
    if action == "soft-push" and len(parts) >= 2:
        channel = parts[0]
        text = " ".join(parts[1:])
        ad = get_adapter(channel)
        if not ad or not hasattr(ad, "soft_push"):
            return json.dumps({"ok": False, "error": "channel lacks soft_push"})
        msg = ad.soft_push(text)
        return json.dumps(
            {"ok": True, "message": {"channel": msg.channel, "sender": msg.sender, "text": msg.text}},
            indent=2,
        )
    return (
        "[channels] actions: list|start <name>|stop <name>|pump|"
        "send <ch> <chat_id> <text>|soft-push <ch> <text>"
    )
