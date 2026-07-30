"""
cli/repl_input.py
=================
Professional REPL input: history + slash autocomplete (ADR-067).

Uses prompt_toolkit when available; falls back to builtin input().
Enable/disable with KERROS_REPL_PT=0 to force plain input.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

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


def _history_path() -> Path:
    p = Path(os.path.expanduser("~/offline_ai")) / "data" / "repl_history"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _extra_commands() -> list[str]:
    extras = [
        "gateway start",
        "gateway status",
        "gateway channel list",
        "list sessions",
        "resume latest",
        "skills hub list",
        "search past sessions",
        "profile memory list",
        "agent cron list",
        "bg list",
    ]
    return extras


def prompt_line(prompt_ansi: str = "") -> str:
    """Read one user line with optional autocomplete/history."""
    if not _use_pt():
        return input(prompt_ansi).strip()
    try:
        from prompt_toolkit import prompt
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import ANSI
        from prompt_toolkit.history import FileHistory
    except Exception:
        return input(prompt_ansi).strip()

    words = list(SLASH_COMMANDS) + _extra_commands()
    completer = WordCompleter(words, ignore_case=True, sentence=True)
    try:
        text = prompt(
            ANSI(prompt_ansi) if prompt_ansi else "",
            history=FileHistory(str(_history_path())),
            completer=completer,
            complete_while_typing=True,
        )
        return (text or "").strip()
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        return input(prompt_ansi).strip()
