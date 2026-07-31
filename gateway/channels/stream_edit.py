"""
gateway/channels/stream_edit.py
================================
Soft progressive message edits (ADR-102).

Instead of one final send, Soft-stream chunks update a local "message id"
and optionally call adapter.edit if present; otherwise records Soft edits
in outbox metadata for demos.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional

from gateway.channels.bridge import iter_channel_reply_chunks


def stream_edit_reply_once(
    *,
    prefix: str = "[KerrOS]",
    on_edit: Optional[Callable[[dict[str, Any]], None]] = None,
) -> dict[str, Any]:
    from gateway import webhook as gw
    from gateway.channels.registry import get_adapter, poll_all, send_channel
    from gateway.channels.routing import index_channel_turn, session_id_for
    from gateway.channels.trace import append_trace

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
        msg_id = "soft-" + uuid.uuid4().hex[:10]
        assembled = ""
        edits = 0
        mode = "soft"
        for ev in iter_channel_reply_chunks(
            m.text, channel=m.channel, sender=m.sender, prefix=prefix
        ):
            if ev.get("type") == "chunk":
                assembled += str(ev.get("text") or "")
                edits += 1
                event = {
                    "message_id": msg_id,
                    "channel": m.channel,
                    "chat_id": m.chat_id,
                    "text": assembled,
                    "edit": edits,
                    "type": "edit",
                }
                ad = get_adapter(m.channel)
                if ad is not None:
                    try:
                        if not hasattr(ad, "_soft_edits"):
                            ad._soft_edits = []
                        if hasattr(ad, "soft_edit"):
                            ad.soft_edit(msg_id, assembled, chat_id=m.chat_id or "soft")
                        else:
                            ad._soft_edits.append(
                                {
                                    "message_id": msg_id,
                                    "chat_id": m.chat_id or "soft",
                                    "text": assembled,
                                }
                            )
                    except Exception:
                        pass
                if on_edit:
                    try:
                        on_edit(event)
                    except Exception:
                        pass
            elif ev.get("type") == "final":
                assembled = str(ev.get("text") or assembled)
                mode = ev.get("mode") or mode
        # Final send (platforms without edit still get one outbound)
        sent = send_channel(m.channel, m.chat_id or "soft", assembled)
        sid = index_channel_turn(
            "user",
            f"[{m.channel}:{m.sender}] {m.text}",
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=m.sender or "",
        )
        index_channel_turn(
            "assistant",
            assembled,
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=m.sender or "",
        )
        append_trace(
            "channel_stream_edit",
            {"channel": m.channel, "edits": edits, "message_id": msg_id, "session_id": sid},
        )
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
                "message_id": msg_id,
                "edits": edits,
                "inbound": m.text,
                "outbound": assembled,
                "mode": mode,
                "send": sent,
            }
        )
    return {"ok": True, "pulled": len(pulled), "replies": replies, "stream_edit": True}
