"""
cli/repl_input.py
=================
Professional REPL input: history + slash autocomplete + multiline (ADR-067/073).

Uses prompt_toolkit when available; falls back to builtin input().
Enable/disable with KERROS_REPL_PT=0 to force plain input.

Multiline: a trailing backslash continues the prompt; lines are joined with
newlines. Set KERROS_REPL_MULTILINE=0 to disable continuation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Core slash commands surfaced for autocomplete (chat.py /help subset).
SLASH_COMMANDS = [
    "/help",
    "/exit",
    "/online",
    "/offline",
    "/mode",
    "/apistatus",
    "/setkey",
    "/tools",
    "/memory",
    "/history",
    "/clear",
    "/recall",
    "/knowledge",
    "/kb",
    "/react",
    "/code",
    "/research",
    "/plan",
    "/analyze",
    "/delegate",
    "/scope",
    "/kernel",
    "/health",
    "/services",
    "/events",
    "/schedule",
    "/integrations",
    "/workflows",
    "/capabilities",
    "/decisions",
    "/llm",
    "/reflect",
    "/reflections",
    "/security",
    "/sources",
    "/gateway",
    "/sessions",
    "/resume",
    "/read",
    "/write",
    "/edit",
    "/list",
    "/exec",
    "/remove",
    "/tool",
    "/workspace",
]


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _use_pt() -> bool:
    if os.environ.get("KERROS_REPL_PT") is not None:
        return _truthy(os.environ.get("KERROS_REPL_PT"))
    # Default on when a TTY is present
    try:
        return os.isatty(0)
    except Exception:
        return False


def _multiline_enabled() -> bool:
    if os.environ.get("KERROS_REPL_MULTILINE") is not None:
        return _truthy(os.environ.get("KERROS_REPL_MULTILINE"))
    return True


def _history_path() -> Path:
    p = Path(os.path.expanduser("~/offline_ai")) / "data" / "repl_history"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _extra_commands() -> list[str]:
    extras = [
        "gateway start",
        "gateway status",
        "gateway channel list",
        "gateway channel start whatsapp",
        "gateway channel soft-reply",
        "gateway channel llm-reply",
        "gateway channel stream-reply",
        "gateway channel slash ping",
        "gateway channel gateway-start",
        "list sessions",
        "resume latest",
        "skills hub list",
        "search past sessions",
        "profile memory list",
        "agent cron list",
        "bg list",
    ]
    return extras


def _prompt_once(prompt_ansi: str = "") -> str:
    """Read a single physical line (may still contain trailing \\)."""
    if not _use_pt():
        return input(prompt_ansi)
    try:
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import ANSI
        from prompt_toolkit.history import FileHistory
    except Exception:
        return input(prompt_ansi)

    words = list(SLASH_COMMANDS) + _extra_commands()
    completer = WordCompleter(words, ignore_case=True, sentence=True)
    try:
        text = prompt(
            ANSI(prompt_ansi) if prompt_ansi else "",
            history=FileHistory(str(_history_path())),
            completer=completer,
            complete_while_typing=True,
        )
        return text if text is not None else ""
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        return input(prompt_ansi)


def join_continued_lines(chunks: list[str]) -> str:
    """Join backslash-continued physical lines (ADR-073)."""
    return "\n".join(chunks).strip()


def prompt_line(prompt_ansi: str = "", *, cont_prompt: Optional[str] = None) -> str:
    """Read one logical user line with optional autocomplete/history/continuation."""
    first = _prompt_once(prompt_ansi)
    if not _multiline_enabled() or not first.rstrip().endswith("\\"):
        return first.strip()

    chunks: list[str] = [first.rstrip()[:-1]]
    cont = cont_prompt if cont_prompt is not None else "  … "
    while True:
        nxt = _prompt_once(cont)
        if nxt.rstrip().endswith("\\"):
            chunks.append(nxt.rstrip()[:-1])
            continue
        chunks.append(nxt)
        break
    return join_continued_lines(chunks)
