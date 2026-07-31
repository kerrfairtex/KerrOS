"""
gateway/channels/tool_loop.py
=============================
Multi-step Soft channel tool loop (ADR-090).

Runs up to N detect_tool/run_tool iterations on inbound text / intermediate
results, then Soft/LLM-summarizes. Deploy tools remain blocked.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from gateway.channels.tool_agent import try_channel_tool, tools_enabled


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def max_steps() -> int:
    try:
        return max(1, min(int(os.environ.get("KERROS_CHANNEL_TOOL_STEPS") or 3), 6))
    except Exception:
        return 3


def run_tool_loop(text: str) -> dict[str, Any]:
    """Execute Soft multi-step tool chain; returns steps + final text."""
    if not tools_enabled():
        return {"ok": True, "steps": [], "final": text, "mode": "passthrough"}
    steps: list[dict[str, Any]] = []
    current = str(text or "")
    for i in range(max_steps()):
        hit = try_channel_tool(current)
        if not hit:
            break
        steps.append({"step": i + 1, **hit})
        if hit.get("blocked"):
            break
        # Feed tool result back as next observation prompt
        current = (
            f"Tool {hit.get('tool')} returned:\n{hit.get('result')}\n"
            f"Original: {text}\nNext Soft action or stop."
        )
        # Stop if result looks terminal
        result = str(hit.get("result") or "")
        if result.startswith("[") and "error" in result.lower():
            break
        if i + 1 < max_steps():
            # Only continue if the next detect would still match something new
            nxt = try_channel_tool(result[:500])
            if not nxt or nxt.get("tool") == hit.get("tool"):
                break
            current = result
    final = steps[-1]["result"] if steps else ""
    return {
        "ok": True,
        "steps": steps,
        "final": str(final)[:4000],
        "mode": "tool-loop" if steps else "none",
        "count": len(steps),
    }


def tool_loop_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    from gateway import webhook as gw
    from gateway.channels.bridge import generate_channel_reply
    from gateway.channels.registry import poll_all, send_channel
    from gateway.channels.routing import index_channel_turn, session_id_for
    from gateway.channels.trace import append_trace

    try:
        from gateway.channels.identity import routed_sender
    except Exception:

        def routed_sender(channel, sender):  # type: ignore
            return sender

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
        sender_key = routed_sender(m.channel, m.sender or "")
        loop = run_tool_loop(m.text)
        if loop.get("steps"):
            outbound = f"{prefix} tools×{loop.get('count')}:\n{loop.get('final')}"[:2000]
            mode = "tool-loop"
        else:
            gen = generate_channel_reply(
                m.text, channel=m.channel, sender=m.sender, prefix=prefix
            )
            outbound = gen["text"]
            mode = gen.get("mode") or "soft"
        sid = index_channel_turn(
            "user",
            f"[{m.channel}:{m.sender}] {m.text}",
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=sender_key,
        )
        index_channel_turn(
            "assistant",
            outbound,
            channel=m.channel,
            chat_id=m.chat_id or "",
            sender=sender_key,
        )
        sent = send_channel(m.channel, m.chat_id or "soft", outbound)
        append_trace(
            "channel_tool_loop",
            {"channel": m.channel, "mode": mode, "steps": loop.get("count"), "session_id": sid},
        )
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", sender_key),
                "inbound": m.text,
                "outbound": outbound,
                "mode": mode,
                "steps": loop.get("steps"),
                "send": sent,
            }
        )
    return {"ok": True, "pulled": len(pulled), "replies": replies}
