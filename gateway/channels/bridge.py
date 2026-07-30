"""
gateway/channels/bridge.py
==========================
LLM-backed channel reply bridge (ADR-074).

Extends ADR-072 Soft acks with an optional generate_complete path when
KERROS_CHANNEL_LLM=1 and an engine is bound. Falls back to Soft ack on
any failure so CI stays deterministic without API keys.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

_engine: Any = None
_generate_fn: Optional[Callable[..., str]] = None


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def llm_enabled() -> bool:
    return _truthy(os.environ.get("KERROS_CHANNEL_LLM"))


def bind_channel_engine(engine: Any = None, *, generate_fn: Optional[Callable[..., str]] = None) -> None:
    """Bind a KerrOS LLM engine (or injectable generate_fn for tests)."""
    global _engine, _generate_fn
    _engine = engine
    _generate_fn = generate_fn


def unbound_channel_engine() -> None:
    bind_channel_engine(None, generate_fn=None)


def _soft_ack(channel: str, text: str, *, prefix: str = "[KerrOS]") -> str:
    return f"{prefix} ack ({channel}): {(text or '')[:200]}"


def generate_channel_reply(
    text: str,
    *,
    channel: str = "channel",
    sender: str = "user",
    prefix: str = "[KerrOS]",
) -> dict[str, Any]:
    """
    Produce a reply string. Returns {text, mode: soft|llm, error?}.
    """
    if not llm_enabled() or (_engine is None and _generate_fn is None):
        return {"text": _soft_ack(channel, text, prefix=prefix), "mode": "soft"}

    prompt = (
        f"You are KerrOS responding on the {channel} messaging channel. "
        f"Sender={sender}. Reply concisely (<=400 chars), no secrets.\n\n"
        f"Message:\n{(text or '')[:1500]}"
    )
    try:
        if _generate_fn is not None:
            out = _generate_fn(prompt)
        else:
            from core.complete import generate_complete

            out = generate_complete(_engine, prompt, stream=False)
        reply = str(out or "").strip()
        if not reply:
            return {
                "text": _soft_ack(channel, text, prefix=prefix),
                "mode": "soft",
                "error": "empty llm reply",
            }
        return {"text": reply[:2000], "mode": "llm"}
    except Exception as exc:
        return {
            "text": _soft_ack(channel, text, prefix=prefix),
            "mode": "soft",
            "error": str(exc),
        }


def llm_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    """Poll channels, index turns, reply via LLM (or Soft fallback), send outbound."""
    from gateway import webhook as gw
    from gateway.channels.registry import poll_all, send_channel

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

        gen = generate_channel_reply(
            m.text, channel=m.channel, sender=m.sender, prefix=prefix
        )
        ack = gen["text"]
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
                "mode": gen.get("mode"),
                "error": gen.get("error"),
                "send": sent,
            }
        )
    return {
        "ok": True,
        "pulled": len(pulled),
        "llm_enabled": llm_enabled(),
        "replies": replies,
    }
