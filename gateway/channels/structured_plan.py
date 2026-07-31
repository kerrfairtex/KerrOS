"""
gateway/channels/structured_plan.py
===================================
Soft structured JSON channel plans (ADR-101).

Accepts either:
  {"steps":[{"action":"tool|reply","text":"..."}, ...]}
or Soft-generates a JSON plan from free text when KERROS_CHANNEL_JSON_PLAN=1
and an LLM/generate_fn is bound (falls back to heuristic splitter).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, List, Optional

from gateway.channels.planner_agent import split_plan
from gateway.channels.tool_loop import run_tool_loop


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def json_plan_enabled() -> bool:
    if os.environ.get("KERROS_CHANNEL_JSON_PLAN") is not None:
        return _truthy(os.environ.get("KERROS_CHANNEL_JSON_PLAN"))
    return True


def parse_structured_plan(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("steps"), list):
                steps = []
                for s in data["steps"][:8]:
                    if isinstance(s, dict) and (s.get("text") or s.get("action")):
                        steps.append(
                            {
                                "action": str(s.get("action") or "reply"),
                                "text": str(s.get("text") or s.get("action") or ""),
                            }
                        )
                if steps:
                    return steps
            if isinstance(data, list):
                steps = []
                for s in data[:8]:
                    if isinstance(s, str):
                        steps.append({"action": "reply", "text": s})
                    elif isinstance(s, dict):
                        steps.append(
                            {
                                "action": str(s.get("action") or "reply"),
                                "text": str(s.get("text") or ""),
                            }
                        )
                if steps:
                    return steps
        except Exception:
            pass
    # Soft LLM plan authoring when bound
    if json_plan_enabled():
        try:
            from gateway.channels import bridge as br

            if br.llm_enabled() and (br._generate_fn or br._engine):
                prompt = (
                    "Return ONLY JSON {\"steps\":[{\"action\":\"tool|reply\",\"text\":\"...\"}]} "
                    "for this task (max 5 steps):\n" + raw[:800]
                )
                if br._generate_fn:
                    out = br._generate_fn(prompt)
                else:
                    from core.complete import generate_complete

                    out = generate_complete(br._engine, prompt, stream=False)
                m = re.search(r"\{.*\}", str(out or ""), re.S)
                if m:
                    return parse_structured_plan(m.group(0))
        except Exception:
            pass
    return [{"action": "reply", "text": s} for s in split_plan(raw)[:8]]


def run_structured_plan(text: str, *, prefix: str = "[KerrOS]") -> dict[str, Any]:
    from gateway.channels.bridge import generate_channel_reply

    steps = parse_structured_plan(text)
    results: List[dict[str, Any]] = []
    for i, step in enumerate(steps, 1):
        action = (step.get("action") or "reply").lower()
        st = str(step.get("text") or "")
        if action == "tool":
            loop = run_tool_loop(st)
            if loop.get("steps"):
                results.append(
                    {
                        "step": i,
                        "action": "tool",
                        "input": st,
                        "output": loop.get("final"),
                        "mode": "tool-loop",
                    }
                )
                continue
        gen = generate_channel_reply(st, channel="plan", sender="plan")
        results.append(
            {
                "step": i,
                "action": action,
                "input": st,
                "output": gen.get("text"),
                "mode": gen.get("mode") or "soft",
            }
        )
    lines = [f"{prefix} json-plan ({len(results)}):"]
    for r in results:
        lines.append(f"{r['step']}. [{r['action']}/{r['mode']}] {str(r.get('output') or '')[:280]}")
    return {"ok": True, "steps": results, "final": "\n".join(lines)[:4000], "count": len(results)}


def structured_plan_reply_once(*, prefix: str = "[KerrOS]") -> dict[str, Any]:
    from gateway import webhook as gw
    from gateway.channels.registry import poll_all, send_channel
    from gateway.channels.routing import index_channel_turn, session_id_for
    from gateway.channels.trace import append_trace

    pulled = poll_all()
    replies = []
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
        plan = run_structured_plan(m.text, prefix=prefix)
        outbound = plan["final"]
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
            "channel_json_plan",
            {"channel": m.channel, "steps": plan.get("count"), "session_id": sid},
        )
        replies.append(
            {
                "channel": m.channel,
                "chat_id": m.chat_id,
                "session_id": sid
                or session_id_for(m.channel, m.chat_id or "", m.sender or ""),
                "inbound": m.text,
                "outbound": outbound,
                "mode": "json-plan",
                "steps": plan.get("steps"),
                "send": sent,
            }
        )
    return {"ok": True, "pulled": len(pulled), "replies": replies}
