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
    from gateway.channels.signal import SignalAdapter
    from gateway.channels.telegram import TelegramAdapter
    from gateway.channels.whatsapp import WhatsAppAdapter

    _adapters["telegram"] = TelegramAdapter()
    _adapters["discord"] = DiscordAdapter()
    _adapters["whatsapp"] = WhatsAppAdapter()
    _adapters["signal"] = SignalAdapter()
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


def soft_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    """
    Soft channel reply loop (ADR-072).

    Poll all running adapters, copy into webhook inbox, index turns into
    session_store, and send a Soft ack outbound per inbound message.
    Does not call an LLM — safe for CI / demos without API keys.
    """
    from gateway import webhook as gw

    pulled = poll_all()
    replies: list[dict[str, Any]] = []
    for m in pulled:
        with gw._lock:
            gw._inbox.append(
                {
                    "channel": m.channel,
                    "sender": m.sender,
                    "text": m.text,
                    "chat_id": m.chat_id,
                }
            )
        try:
            from memory.session_store import index_turn

            index_turn(
                "user",
                f"[{m.channel}:{m.sender}] {m.text}",
                source=f"channel:{m.channel}",
            )
        except Exception:
            pass
        ack = f"{prefix} ack ({m.channel}): {m.text[:200]}"
        sent = send_channel(m.channel, m.chat_id or "soft", ack)
        try:
            from memory.session_store import index_turn

            index_turn("assistant", ack, source=f"channel:{m.channel}")
        except Exception:
            pass
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "inbound": m.text,
                "outbound": ack,
                "send": sent,
            }
        )
    return {"ok": True, "pulled": len(pulled), "replies": replies}


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
    if action in ("soft-reply", "reply-once", "soft_reply"):
        return json.dumps(soft_reply_once(), indent=2)
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
    if action == "soft-webhook" and len(parts) >= 2:
        # soft-webhook whatsapp :: {"entry":[...]}
        channel = parts[0]
        body = " ".join(parts[1:]).strip()
        if body.startswith("::"):
            body = body[2:].strip()
        ad = get_adapter(channel)
        if not ad or not hasattr(ad, "soft_push_webhook"):
            return json.dumps({"ok": False, "error": "channel lacks soft_push_webhook"})
        try:
            payload = json.loads(body)
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"invalid json: {exc}"})
        msgs = ad.soft_push_webhook(payload)
        return json.dumps(
            {
                "ok": True,
                "enqueued": len(msgs),
                "messages": [
                    {"channel": m.channel, "sender": m.sender, "text": m.text} for m in msgs
                ],
            },
            indent=2,
        )
    return (
        "[channels] actions: list|start <name>|stop <name>|pump|soft-reply|"
        "send <ch> <chat_id> <text>|soft-push <ch> <text>|"
        "soft-webhook <ch> <json>"
    )
