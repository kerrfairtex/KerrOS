"""
memory/dreaming.py
==================
Periodic batch that reviews recent session transcripts and organizes /
enriches agent memory stores (ADR-106).

Heuristic by default (no LLM). Optional Soft LLM when KERROS_MEMORY_DREAMING=1
and an engine is provided. Registerable as an agent cron prompt.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from typing import Any, Optional

from memory import unified_store as us


def dreaming_enabled() -> bool:
    env = os.environ.get("KERROS_MEMORY_DREAMING", "").strip().lower()
    if env in ("1", "true", "on", "yes"):
        return True
    try:
        from kernel.config import load_config

        block = (load_config().get("kerros_memory") or {}).get("dreaming") or {}
        return bool(block.get("enabled", False))
    except Exception:
        return False


def _recent_turns(limit: int = 80) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    try:
        from memory.session_store import list_sessions, browse_session

        for sess in list_sessions()[:8]:
            sid = sess.get("session_id") or sess.get("id")
            if not sid:
                continue
            detail = browse_session(str(sid))
            for t in (detail.get("turns") or detail.get("messages") or [])[-20:]:
                turns.append(
                    {
                        "session_id": sid,
                        "role": t.get("role"),
                        "content": (t.get("content") or "")[:500],
                    }
                )
            if len(turns) >= limit:
                break
    except Exception:
        pass
    if not turns:
        try:
            from memory.manager import get_history

            for m in get_history(n=min(limit, 30)):
                turns.append(
                    {
                        "session_id": us.current_session_id(),
                        "role": m.get("role"),
                        "content": (m.get("content") or "")[:500],
                    }
                )
        except Exception:
            pass
    return turns[:limit]


_PREF = re.compile(
    r"\b(prefer|please always|don't|do not|never|timezone|signature|digest)\b",
    re.I,
)
_TASK = re.compile(r"\b(todo|task|follow[- ]?up|remind|deadline|ship|deploy)\b", re.I)
_CONTACT = re.compile(r"\b([A-Z][a-z]+@[A-Za-z0-9._-]*)\b")


def _heuristic_insights(turns: list[dict[str, Any]]) -> dict[str, Any]:
    prefs: list[str] = []
    tasks: list[str] = []
    contacts: Counter[str] = Counter()
    for t in turns:
        text = (t.get("content") or "").strip()
        if not text or t.get("role") not in ("user", "assistant"):
            continue
        if _PREF.search(text) and t.get("role") == "user":
            prefs.append(text[:240])
        if _TASK.search(text):
            tasks.append(f"- ({t.get('session_id')}) {text[:200]}")
        for m in _CONTACT.findall(text):
            contacts[m] += 1
    return {
        "prefs": prefs[:8],
        "tasks": tasks[:12],
        "contacts": contacts.most_common(12),
        "turn_count": len(turns),
    }


def dream(
    *,
    session_id: str = "",
    agent: str = "dreaming",
    apply: bool = True,
    engine: Any = None,
) -> dict[str, Any]:
    """
    Review recent transcripts → organize scout/team memory.

    Soft: when dreaming_enabled() and engine is set, may ask LLM for a short
    structured enrichment; otherwise pure heuristics.
    """
    us.ensure_defaults()
    sid = session_id or us.current_session_id()
    us.bootstrap_session(sid, agent=agent)
    turns = _recent_turns()
    insights = _heuristic_insights(turns)
    updates: list[dict[str, Any]] = []

    def _write(store: str, path: str, content: str, reason: str) -> dict[str, Any]:
        cur = us.read(store, path)
        out = us.write(
            store,
            path,
            content,
            expected_sha256=cur.get("sha256"),
            session_id=sid,
            agent=agent,
            reason=reason,
        )
        if out.get("conflict"):
            cur = us.read(store, path)
            out = us.write(
                store,
                path,
                content,
                expected_sha256=cur.get("sha256"),
                session_id=sid,
                agent=agent,
                reason=reason + " (retry)",
            )
        return out

    # Optional Soft LLM pass (never required)
    llm_note = None
    if dreaming_enabled() and engine is not None:
        try:
            prompt = (
                "Summarize durable user preferences and open tasks from these turns "
                "as short bullet lines. No secrets.\n\n"
                + "\n".join(
                    f"{t.get('role')}: {t.get('content')}" for t in turns[-40:]
                )[:4000]
            )
            if hasattr(engine, "generate"):
                llm_note = engine.generate(prompt)
            elif callable(engine):
                llm_note = engine(prompt)
        except Exception as exc:
            llm_note = f"[dreaming llm soft-skip: {exc}]"

    if not apply:
        return {
            "ok": True,
            "applied": False,
            "insights": insights,
            "llm_note": llm_note,
            "session_id": sid,
        }

    if insights["prefs"]:
        path = "notes/user_preference.md"
        cur = us.read("scout", path)
        body = cur.get("content") or ""
        block = "\n## Dreaming insights ({})\n{}\n".format(
            time.strftime("%Y-%m-%d"),
            "\n".join(f"- {p}" for p in insights["prefs"]),
        )
        if block.strip() not in body:
            updates.append(
                _write("scout", path, body.rstrip() + "\n" + block, "dreaming prefs")
            )

    if insights["contacts"]:
        path = "notes/recurring_contact.md"
        cur = us.read("scout", path)
        body = cur.get("content") or ""
        lines = [
            f"| {name} | inferred | seen {n}x in recent sessions |"
            for name, n in insights["contacts"]
            if name.lower() not in body.lower()
        ]
        if lines:
            block = "\n## Dreaming contacts\n" + "\n".join(lines) + "\n"
            updates.append(
                _write("scout", path, body.rstrip() + "\n" + block, "dreaming contacts")
            )

    if insights["tasks"]:
        path = "task/complete.md"
        cur = us.read("scout", path)
        body = cur.get("content") or ""
        block = "\n## Dreaming open signals\n" + "\n".join(insights["tasks"]) + "\n"
        updates.append(
            _write("scout", path, body.rstrip() + "\n" + block, "dreaming tasks")
        )

    flash = us.read("team", "flash_task.md")
    note = (
        f"\n## Dream {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"- turns_reviewed: {insights['turn_count']}\n"
        f"- prefs_signals: {len(insights['prefs'])}\n"
        f"- task_signals: {len(insights['tasks'])}\n"
        f"- contacts: {len(insights['contacts'])}\n"
    )
    if llm_note:
        note += f"- llm: {str(llm_note)[:400]}\n"
    updates.append(
        _write(
            "team",
            "flash_task.md",
            (flash.get("content") or "").rstrip() + "\n" + note,
            "dreaming team flash",
        )
    )

    # Graph enrichment
    try:
        from tools.memory_graph import remember_entities

        remember_entities(
            [c for c, _ in insights["contacts"]],
            kind="contact",
            session_id=sid,
            agent=agent,
        )
    except Exception:
        pass

    return {
        "ok": True,
        "applied": True,
        "insights": {
            "prefs": len(insights["prefs"]),
            "tasks": len(insights["tasks"]),
            "contacts": len(insights["contacts"]),
            "turn_count": insights["turn_count"],
        },
        "updates": updates,
        "session_id": sid,
        "ts": time.time(),
    }


def register_dreaming_cron() -> dict[str, Any]:
    """Soft-register a daily dreaming cron job (idempotent by name)."""
    try:
        from runtime.agent_jobs import create_job, list_jobs

        for j in list_jobs():
            if j.get("name") == "memory-dreaming":
                return {"ok": True, "exists": True, "id": j.get("id")}
        return create_job(
            "memory-dreaming",
            "0 3 * * *",
            "Run KerrOS memory dreaming: organize scout/team stores from recent sessions.",
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def tool_dream(raw: str) -> str:
    text = (raw or "run").strip().lower()
    if text in ("register", "cron"):
        return json.dumps(register_dreaming_cron(), indent=2)
    apply = text not in ("dry", "dry-run", "preview")
    return json.dumps(dream(apply=apply), indent=2)
