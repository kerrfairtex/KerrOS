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
        # ADR-075: Discord Gateway Soft/live inbox
        try:
            from gateway.channels.discord_gateway import get_discord_gateway

            gw = get_discord_gateway()
            msgs.extend(gw.poll_messages() or [])
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
    Soft channel reply loop (ADR-072 + ADR-079 routing).

    Poll all running adapters, copy into webhook inbox, index turns into
    per-channel routed sessions, and send a Soft ack outbound per inbound.
    Does not call an LLM — safe for CI / demos without API keys.
    """
    from gateway import webhook as gw
    from gateway.channels.routing import index_channel_turn, session_id_for

    from gateway.channels.rate_limit import allow as rate_allow

    pulled = poll_all()
    replies: list[dict[str, Any]] = []
    for m in pulled:
        rate = rate_allow(m.channel, m.chat_id or "", m.sender or "")
        if not rate.get("allowed"):
            replies.append(
                {
                    "channel": m.channel,
                    "chat_id": m.chat_id,
                    "inbound": m.text,
                    "outbound": "",
                    "mode": "rate-limited",
                    "rate": rate,
                    "send": {"ok": False, "error": "rate limited"},
                }
            )
            continue
        with gw._lock:
            gw._inbox.append(
                {
                    "channel": m.channel,
                    "sender": m.sender,
                    "text": m.text,
                    "chat_id": m.chat_id,
                }
            )
        ack = f"{prefix} ack ({m.channel}): {m.text[:200]}"
        sid = index_channel_turn(
            "user",
            f"[{m.channel}:{m.sender}] {m.text}",
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=m.sender or "",
        )
        index_channel_turn(
            "assistant",
            ack,
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=m.sender or "",
        )
        sent = send_channel(m.channel, m.chat_id or "soft", ack)
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
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
    if action in ("llm-reply", "llm_reply", "reply-llm"):
        from gateway.channels.bridge import llm_reply_once

        return json.dumps(llm_reply_once(), indent=2)
    if action in ("stream-reply", "stream_reply", "reply-stream"):
        from gateway.channels.bridge import stream_reply_once

        return json.dumps(stream_reply_once(), indent=2)
    if action in ("tool-reply", "tool_reply", "reply-tools"):
        from gateway.channels.tool_agent import tool_reply_once

        return json.dumps(tool_reply_once(), indent=2)
    if action in ("tool-loop", "tool_loop", "loop-reply"):
        from gateway.channels.tool_loop import tool_loop_reply_once

        return json.dumps(tool_loop_reply_once(), indent=2)
    if action in ("plan-reply", "planner", "planner-reply"):
        from gateway.channels.planner_agent import planner_reply_once

        return json.dumps(planner_reply_once(), indent=2)
    if action in ("signal-ingest", "signal_ingest") and parts:
        from gateway.channels.signal_relay import ingest_signal_payload

        body = " ".join(parts).strip()
        if body.startswith("::"):
            body = body[2:].strip()
        try:
            payload = json.loads(body)
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"invalid json: {exc}"})
        return json.dumps(ingest_signal_payload(payload), indent=2)
    if action in ("trace", "trace-list"):
        from gateway.channels.trace import format_trace

        return format_trace(limit=30)
    if action in ("trace-export", "export-trace"):
        from gateway.channels.export import export_trace

        fmt = parts[0] if parts else "json"
        return json.dumps(export_trace(format=fmt), indent=2)
    if action in ("siem-push", "siem_push", "push-siem"):
        from gateway.channels.siem_push import push_trace

        fmt = parts[0] if parts else "json"
        return json.dumps(push_trace(format=fmt), indent=2)
    if action in ("identity", "id") and parts:
        from gateway.channels import identity as ident

        sub = parts[0].lower()
        rest = parts[1:]
        if sub == "list":
            return json.dumps(ident.list_identities(), indent=2)
        if sub == "link" and len(rest) >= 2:
            # identity link telegram alice [id-xxx]
            ch, sender = rest[0], rest[1]
            iid = rest[2] if len(rest) > 2 else None
            return json.dumps(ident.link_identity(ch, sender, identity_id=iid), indent=2)
        if sub == "unlink" and len(rest) >= 2:
            return json.dumps(ident.unlink_alias(rest[0], rest[1]), indent=2)
        if sub == "resolve" and len(rest) >= 2:
            return json.dumps(
                {"ok": True, "identity_id": ident.resolve_identity(rest[0], rest[1])},
                indent=2,
            )
        return "[identity] link <ch> <sender> [id] | unlink <ch> <sender> | resolve <ch> <sender> | list"
    if action in ("slash", "slash-dispatch", "discord-slash") and parts:
        from gateway.channels.slash import handle_slash_command

        name = parts[0].lstrip("/")
        body = " ".join(parts[1:]).strip()
        if body.startswith("::"):
            body = body[2:].strip()
        opts: dict[str, Any] = {}
        if body:
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    opts = parsed
            except Exception:
                opts = {"_raw": body}
        return json.dumps(handle_slash_command(name, opts), indent=2)
    if action in ("gateway-start", "discord-gateway-start"):
        from gateway.channels.discord_gateway import get_discord_gateway

        return json.dumps(get_discord_gateway().start(), indent=2)
    if action in ("gateway-stop", "discord-gateway-stop"):
        from gateway.channels.discord_gateway import get_discord_gateway

        return json.dumps(get_discord_gateway().stop(), indent=2)
    if action in ("gateway-status", "discord-gateway-status"):
        from gateway.channels.discord_gateway import get_discord_gateway

        return json.dumps(get_discord_gateway().status(), indent=2)
    if action in ("gateway-dispatch", "discord-gateway-dispatch") and len(parts) >= 2:
        # gateway-dispatch MESSAGE_CREATE :: {"content":"hi","channel_id":"1","author":{"username":"a"}}
        from gateway.channels.discord_gateway import get_discord_gateway

        event = parts[0]
        body = " ".join(parts[1:]).strip()
        if body.startswith("::"):
            body = body[2:].strip()
        try:
            data = json.loads(body) if body else {}
        except Exception as exc:
            return json.dumps({"ok": False, "error": f"invalid json: {exc}"})
        return json.dumps(get_discord_gateway().soft_dispatch(event, data), indent=2)
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
        "[channels] actions: list|start <name>|stop <name>|pump|soft-reply|llm-reply|"
        "stream-reply|tool-reply|tool-loop|plan-reply|signal-ingest <json>|"
        "trace|trace-export [json|cef]|siem-push [json|cef]|"
        "identity link|unlink|resolve|list|slash <name> [json]|"
        "gateway-start|gateway-stop|gateway-status|gateway-dispatch <EVENT> <json>|"
        "send <ch> <chat_id> <text>|soft-push <ch> <text>|"
        "soft-webhook <ch> <json>"
    )
