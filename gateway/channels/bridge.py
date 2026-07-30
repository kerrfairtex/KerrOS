"""
gateway/channels/bridge.py
==========================
LLM-backed channel reply bridge (ADR-074) + streaming Soft chunks (ADR-080).

Extends ADR-072 Soft acks with an optional generate_complete path when
KERROS_CHANNEL_LLM=1 and an engine is bound. Falls back to Soft ack on
any failure so CI stays deterministic without API keys.

ADR-079: per-channel session routing via gateway.channels.routing.
ADR-080: stream_reply_once emits Soft progressive chunks (and optional
callback) before the final send.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Iterator, Optional

_engine: Any = None
_generate_fn: Optional[Callable[..., str]] = None
_stream_fn: Optional[Callable[..., Iterator[str]]] = None


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def llm_enabled() -> bool:
    return _truthy(os.environ.get("KERROS_CHANNEL_LLM"))


def stream_enabled() -> bool:
    if os.environ.get("KERROS_CHANNEL_STREAM") is not None:
        return _truthy(os.environ.get("KERROS_CHANNEL_STREAM"))
    return True


def bind_channel_engine(
    engine: Any = None,
    *,
    generate_fn: Optional[Callable[..., str]] = None,
    stream_fn: Optional[Callable[..., Iterator[str]]] = None,
) -> None:
    """Bind a KerrOS LLM engine (or injectable generate/stream fn for tests)."""
    global _engine, _generate_fn, _stream_fn
    _engine = engine
    _generate_fn = generate_fn
    _stream_fn = stream_fn


def unbound_channel_engine() -> None:
    bind_channel_engine(None, generate_fn=None, stream_fn=None)


def _soft_ack(channel: str, text: str, *, prefix: str = "[KerrOS]") -> str:
    return f"{prefix} ack ({channel}): {(text or '')[:200]}"


def soft_chunk_text(text: str, *, size: int = 40) -> list[str]:
    """Split text into Soft stream chunks (ADR-080)."""
    t = text or ""
    if not t:
        return []
    n = max(8, int(size))
    return [t[i : i + n] for i in range(0, len(t), n)]


def generate_channel_reply(
    text: str,
    *,
    channel: str = "channel",
    sender: str = "user",
    prefix: str = "[KerrOS]",
) -> dict[str, Any]:
    """Produce a reply string. Returns {text, mode: soft|llm, error?}."""
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


def iter_channel_reply_chunks(
    text: str,
    *,
    channel: str = "channel",
    sender: str = "user",
    prefix: str = "[KerrOS]",
) -> Iterator[dict[str, Any]]:
    """
    Yield Soft stream events: {type: chunk|final, text, mode, ...}.
    """
    if llm_enabled() and _stream_fn is not None:
        buf: list[str] = []
        try:
            prompt = (
                f"You are KerrOS on {channel}. Sender={sender}. "
                f"Reply briefly.\n\n{(text or '')[:1500]}"
            )
            for piece in _stream_fn(prompt):
                chunk = str(piece or "")
                if not chunk:
                    continue
                buf.append(chunk)
                yield {"type": "chunk", "text": chunk, "mode": "llm"}
            final = "".join(buf).strip() or _soft_ack(channel, text, prefix=prefix)
            yield {"type": "final", "text": final[:2000], "mode": "llm"}
            return
        except Exception as exc:
            ack = _soft_ack(channel, text, prefix=prefix)
            yield {"type": "final", "text": ack, "mode": "soft", "error": str(exc)}
            return

    gen = generate_channel_reply(
        text, channel=channel, sender=sender, prefix=prefix
    )
    full = gen["text"]
    if stream_enabled():
        for chunk in soft_chunk_text(full):
            yield {"type": "chunk", "text": chunk, "mode": gen.get("mode")}
    yield {
        "type": "final",
        "text": full,
        "mode": gen.get("mode"),
        "error": gen.get("error"),
    }


def _index_pair(m: Any, outbound: str) -> Optional[str]:
    from gateway.channels.routing import index_channel_turn

    sid = index_channel_turn(
        "user",
        f"[{m.channel}:{m.sender}] {m.text}",
        channel=m.channel,
        chat_id=m.chat_id or "",
        sender=m.sender or "",
    )
    index_channel_turn(
        "assistant",
        outbound,
        channel=m.channel,
        chat_id=m.chat_id or "",
        sender=m.sender or "",
    )
    return sid


def llm_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    """Poll channels, index into routed sessions, reply via LLM/Soft, send."""
    from gateway import webhook as gw
    from gateway.channels.registry import poll_all, send_channel
    from gateway.channels.routing import session_id_for

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
        gen = generate_channel_reply(
            m.text, channel=m.channel, sender=m.sender, prefix=prefix
        )
        ack = gen["text"]
        sid = _index_pair(m, ack)
        sent = send_channel(m.channel, m.chat_id or "soft", ack)
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
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


def stream_reply_once(
    *,
    prefix: str = "[KerrOS]",
    on_chunk: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    """
    ADR-080: Soft-stream chunks then send the final reply (one outbound).
    """
    from gateway import webhook as gw
    from gateway.channels.registry import poll_all, send_channel
    from gateway.channels.routing import session_id_for

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
        chunks: list[str] = []
        final_text = ""
        mode = "soft"
        err = None
        for ev in iter_channel_reply_chunks(
            m.text, channel=m.channel, sender=m.sender, prefix=prefix
        ):
            if on_chunk:
                try:
                    on_chunk({"channel": m.channel, **ev})
                except Exception:
                    pass
            if ev.get("type") == "chunk":
                chunks.append(str(ev.get("text") or ""))
            elif ev.get("type") == "final":
                final_text = str(ev.get("text") or "")
                mode = ev.get("mode") or mode
                err = ev.get("error")
        sid = _index_pair(m, final_text)
        sent = send_channel(m.channel, m.chat_id or "soft", final_text)
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
                "inbound": m.text,
                "outbound": final_text,
                "chunks": len(chunks),
                "mode": mode,
                "error": err,
                "send": sent,
            }
        )
    return {
        "ok": True,
        "pulled": len(pulled),
        "stream": True,
        "llm_enabled": llm_enabled(),
        "replies": replies,
    }
