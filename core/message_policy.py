"""
core/message_policy.py
======================
Strict-ish message role alternation + context compression trigger (ADR-057).
"""

from __future__ import annotations

from typing import Any, Optional


def _tokens(text: str) -> int:
    return max(0, len(text or "") // 4)


def messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages or []:
        total += _tokens(str(m.get("content") or ""))
        total += 4  # role overhead heuristic
    return total


def validate_alternation(
    messages: list[dict[str, Any]],
    *,
    repair: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Ensure top-level user/assistant alternation.

    Tool/system messages are preserved but do not break the user/assistant
    cadence check. Returns (messages, warnings).
    """
    warnings: list[str] = []
    if not messages:
        return [], warnings

    out: list[dict[str, Any]] = []
    last_ua: Optional[str] = None
    for raw in messages:
        if not isinstance(raw, dict):
            warnings.append("dropped_non_dict_message")
            continue
        role = str(raw.get("role") or "").strip().lower()
        content = raw.get("content")
        if role not in ("user", "assistant", "system", "tool"):
            warnings.append(f"unknown_role:{role}")
            if not repair:
                continue
            role = "user"
        msg = {"role": role, "content": content}
        for k, v in raw.items():
            if k not in msg:
                msg[k] = v

        if role in ("system", "tool"):
            out.append(msg)
            continue

        if last_ua == role:
            warnings.append(f"duplicate_role:{role}")
            if repair:
                # Merge into previous same-role turn when possible.
                for i in range(len(out) - 1, -1, -1):
                    if out[i].get("role") == role:
                        prev = str(out[i].get("content") or "")
                        cur = str(content or "")
                        out[i]["content"] = (prev + "\n" + cur).strip()
                        break
                else:
                    out.append(msg)
                continue
        out.append(msg)
        last_ua = role

    # Prefer starting with user for chat histories (drop leading assistant).
    for i, m in enumerate(out):
        if m.get("role") == "user":
            if i > 0 and repair:
                warnings.append("trimmed_leading_non_user")
                out = out[i:]
            break
    return out, warnings


def should_compress(
    messages: list[dict[str, Any]],
    *,
    context_size: int,
    max_tokens: int,
    ratio: float = 0.5,
) -> bool:
    usable = max(256, int(context_size) - int(max_tokens) - 64)
    threshold = int(usable * ratio)
    return messages_tokens(messages) >= threshold


def compress_messages(
    messages: list[dict[str, Any]],
    *,
    keep_last: int = 6,
) -> list[dict[str, Any]]:
    if len(messages) <= keep_last + 1:
        return messages
    old, recent = messages[:-keep_last], messages[-keep_last:]
    bits: list[str] = []
    for m in old:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        bits.append(f"{role}: {str(m.get('content') or '')[:80]}")
    summary = " | ".join(bits)
    if len(summary) > 1200:
        summary = summary[:1200] + "…"
    compressed = {
        "role": "system",
        "content": f"[Earlier turns compressed]: {summary}",
    }
    return [compressed] + recent


def prepare_history(
    messages: list[dict[str, Any]],
    *,
    context_size: int = 4096,
    max_tokens: int = 512,
    repair: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cleaned, warnings = validate_alternation(messages, repair=repair)
    meta: dict[str, Any] = {
        "warnings": warnings,
        "tokens_before": messages_tokens(messages),
        "compressed": False,
    }
    if should_compress(cleaned, context_size=context_size, max_tokens=max_tokens):
        cleaned = compress_messages(cleaned)
        meta["compressed"] = True
    meta["tokens_after"] = messages_tokens(cleaned)
    return cleaned, meta
