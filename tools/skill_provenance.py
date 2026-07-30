"""
tools/skill_provenance.py
=========================
Write-origin ContextVar for skill creates (ADR-064).

Distinguishes foreground user-directed writes from background review/auto
skill creation so curators only auto-manage agent-created skills.
"""

from __future__ import annotations

import contextvars

_write_origin: contextvars.ContextVar[str] = contextvars.ContextVar(
    "skill_write_origin",
    default="foreground",
)

BACKGROUND_REVIEW = "background_review"


def set_current_write_origin(origin: str) -> contextvars.Token:
    return _write_origin.set(origin or "foreground")


def reset_current_write_origin(token: contextvars.Token) -> None:
    _write_origin.reset(token)


def get_current_write_origin() -> str:
    return _write_origin.get()


def is_background_review() -> bool:
    return get_current_write_origin() == BACKGROUND_REVIEW
