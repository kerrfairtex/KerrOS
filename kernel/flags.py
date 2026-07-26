"""Small helpers for parsing boolean feature flags."""

from __future__ import annotations

from typing import Any


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

