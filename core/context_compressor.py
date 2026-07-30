"""
core/context_compressor.py
==========================
Deeper context compression (ADR-063).

Builds on ADR-057 message_policy:
  1) prune oversized tool/system blobs
  2) extractive fold of middle turns
  3) optional Soft LLM summarize (KERROS_LLM_COMPRESS=1)

Never prints secrets; fails soft to extractive summary.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from core.message_policy import compress_messages, messages_tokens, validate_alternation


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def prune_tool_outputs(messages: list[dict[str, Any]], *, max_tool_chars: int = 800) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        msg = dict(m)
        role = str(msg.get("role") or "")
        content = str(msg.get("content") or "")
        if role in ("tool", "system") and len(content) > max_tool_chars:
            msg["content"] = content[:max_tool_chars] + "…[pruned]"
        out.append(msg)
    return out


def structured_extractive_summary(messages: list[dict[str, Any]], *, max_chars: int = 1400) -> str:
    resolved: list[str] = []
    pending: list[str] = []
    for m in messages:
        role = m.get("role")
        text = str(m.get("content") or "").strip()
        if not text or role not in ("user", "assistant"):
            continue
        snippet = text[:120].replace("\n", " ")
        if role == "user":
            pending.append(snippet)
        else:
            if pending:
                resolved.append(f"Q: {pending.pop(0)} → A: {snippet}")
            else:
                resolved.append(f"A: {snippet}")
    parts = []
    if resolved:
        parts.append("Resolved: " + " | ".join(resolved[-8:]))
    if pending:
        parts.append("Pending: " + " | ".join(pending[-4:]))
    summary = " ".join(parts) or "No prior user/assistant turns."
    if len(summary) > max_chars:
        summary = summary[:max_chars] + "…"
    return summary


def llm_summarize(messages: list[dict[str, Any]], engine: Any) -> Optional[str]:
    if not _truthy(os.environ.get("KERROS_LLM_COMPRESS")):
        return None
    if engine is None:
        return None
    try:
        from core.complete import generate_complete

        body = structured_extractive_summary(messages, max_chars=2000)
        prompt = (
            "Compress this conversation history into <=8 short bullets. "
            "Label Resolved vs Pending. Do not invent facts. No secrets.\n\n"
            + body
        )
        out = generate_complete(engine, prompt, stream=False)
        text = str(out or "").strip()
        return text[:2000] if text else None
    except Exception:
        return None


def compress_context(
    messages: list[dict[str, Any]],
    *,
    keep_last: int = 6,
    engine: Any = None,
    context_size: int = 4096,
    max_tokens: int = 512,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cleaned, warnings = validate_alternation(messages, repair=True)
    pruned = prune_tool_outputs(cleaned)
    meta: dict[str, Any] = {
        "warnings": warnings,
        "tokens_before": messages_tokens(messages),
        "mode": "none",
    }
    usable = max(256, int(context_size) - int(max_tokens) - 64)
    if messages_tokens(pruned) < int(usable * 0.5):
        meta["tokens_after"] = messages_tokens(pruned)
        return pruned, meta

    if len(pruned) <= keep_last + 1:
        meta["tokens_after"] = messages_tokens(pruned)
        return pruned, meta

    old, recent = pruned[:-keep_last], pruned[-keep_last:]
    llm = llm_summarize(old, engine)
    if llm:
        summary = {"role": "system", "content": f"[Compressed context — LLM]: {llm}"}
        meta["mode"] = "llm"
    else:
        summary = {
            "role": "system",
            "content": f"[Compressed context]: {structured_extractive_summary(old)}",
        }
        meta["mode"] = "extractive"
        # Also fold via message_policy for compatibility
        _ = compress_messages(pruned, keep_last=keep_last)
    out = [summary] + recent
    meta["tokens_after"] = messages_tokens(out)
    return out, meta
