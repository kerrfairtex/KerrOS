"""
gateway/channels/planner_agent.py
=================================
Soft planner-backed channel agent (ADR-093).

Splits inbound text on `;` / newlines / ` then ` into Soft plan steps,
runs tool-loop or Soft/LLM per step, and returns a combined reply.
"""

from __future__ import annotations

import os
import re
from typing import Any, List

from gateway.channels.tool_loop import run_tool_loop


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def planner_enabled() -> bool:
    if os.environ.get("KERROS_CHANNEL_PLANNER") is not None:
        return _truthy(os.environ.get("KERROS_CHANNEL_PLANNER"))
    return True


def split_plan(text: str) -> List[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    # Prefer explicit separators
    if "\n" in raw or ";" in raw or re.search(r"\bthen\b", raw, re.I):
        parts = re.split(r"(?:\n+|;|\bthen\b)", raw, flags=re.I)
        steps = [p.strip(" -\t") for p in parts if p and p.strip(" -\t")]
        return steps[:8] or [raw]
    return [raw]


def run_plan(text: str, *, prefix: str = "[KerrOS]") -> dict[str, Any]:
    from gateway.channels.bridge import generate_channel_reply

    steps = split_plan(text)
    results: list[dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        loop = run_tool_loop(step)
        if loop.get("steps"):
            results.append(
                {
                    "step": i,
                    "input": step,
                    "mode": "tool-loop",
                    "output": loop.get("final"),
                    "tools": loop.get("count"),
                }
            )
        else:
            gen = generate_channel_reply(step, channel="planner", sender="plan")
            results.append(
                {
                    "step": i,
                    "input": step,
                    "mode": gen.get("mode") or "soft",
                    "output": gen.get("text"),
                }
            )
    lines = [f"{prefix} plan ({len(results)} step(s)):"]
    for r in results:
        lines.append(f"{r['step']}. ({r['mode']}) {str(r.get('output') or '')[:300]}")
    return {
        "ok": True,
        "steps": results,
        "final": "\n".join(lines)[:4000],
        "count": len(results),
    }


def planner_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    from gateway import webhook as gw
    from gateway.channels.bridge import generate_channel_reply
    from gateway.channels.registry import poll_all, send_channel
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
        if planner_enabled():
            plan = run_plan(m.text, prefix=prefix)
            outbound = plan["final"]
            mode = "planner"
            steps = plan.get("steps")
        else:
            gen = generate_channel_reply(
                m.text, channel=m.channel, sender=m.sender, prefix=prefix
            )
            outbound = gen["text"]
            mode = gen.get("mode") or "soft"
            steps = None
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
        sent = send_channel(m.channel, m.chat_id or "soft", outbound)
        append_trace(
            "channel_planner",
            {"channel": m.channel, "mode": mode, "steps": len(steps or []), "session_id": sid},
        )
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
                "inbound": m.text,
                "outbound": outbound,
                "mode": mode,
                "steps": steps,
                "send": sent,
            }
        )
    return {
        "ok": True,
        "pulled": len(pulled),
        "planner_enabled": planner_enabled(),
        "replies": replies,
    }
