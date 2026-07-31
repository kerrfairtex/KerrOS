"""
gateway/channels/tool_agent.py
==============================
Soft tool-using channel agent (ADR-085).

For each inbound message, try KerrOS detect_tool / run_tool. If no tool
matches, fall back to Soft ack or LLM bridge reply.
"""

from __future__ import annotations

import os
from typing import Any, Optional


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def tools_enabled() -> bool:
    if os.environ.get("KERROS_CHANNEL_TOOLS") is not None:
        return _truthy(os.environ.get("KERROS_CHANNEL_TOOLS"))
    return True


def try_channel_tool(text: str) -> Optional[dict[str, Any]]:
    """Return {tool, args, result} if a Soft-safe tool matched, else None."""
    if not tools_enabled():
        return None
    try:
        from kernel.access import detect_tool, run_tool
    except Exception:
        try:
            from kernel.router import detect_tool, run_tool
        except Exception:
            return None
    try:
        tool, args = detect_tool(str(text or ""), bypass_gate=True)
    except TypeError:
        try:
            tool, args = detect_tool(str(text or ""))
        except Exception:
            return None
    except Exception:
        return None
    if not tool:
        return None
    # Block obviously dangerous / deploy tools in Soft channel path
    blocked = {
        "github_push",
        "vercel_deploy",
        "netlify_deploy",
        "railway_deploy",
        "cloudflare_deploy",
        "supabase_migrate",
        "stripe_trigger",
        "self_run",
    }
    if tool in blocked:
        return {
            "tool": tool,
            "args": args,
            "result": f"[channel tools] blocked tool '{tool}' on messaging bridge",
            "blocked": True,
        }
    try:
        result = run_tool(tool, args)
    except Exception as exc:
        return {"tool": tool, "args": args, "result": f"[tool error] {exc}", "error": str(exc)}
    return {"tool": tool, "args": args, "result": str(result)[:4000]}


def tool_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    """Poll → try tools → else Soft/LLM reply; index + send."""
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
        tool_hit = try_channel_tool(m.text)
        if tool_hit:
            outbound = f"{prefix} tool:{tool_hit.get('tool')}\n{tool_hit.get('result')}"[:2000]
            mode = "tool"
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
            "channel_tool" if tool_hit else "channel_reply",
            {
                "channel": m.channel,
                "mode": mode,
                "tool": (tool_hit or {}).get("tool"),
                "session_id": sid,
            },
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
                "tool": (tool_hit or {}).get("tool"),
                "send": sent,
            }
        )
    return {"ok": True, "pulled": len(pulled), "tools_enabled": tools_enabled(), "replies": replies}
