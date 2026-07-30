"""
gateway/channels/routing.py
===========================
Per-channel session routing (ADR-079).

Maps (channel, chat_id, sender) → stable session_id so Soft/LLM channel
bridges index turns into isolated threads instead of the REPL session.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from typing import Any, Optional

_lock = threading.RLock()
_cache: dict[str, str] = {}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def routing_enabled() -> bool:
    if os.environ.get("KERROS_CHANNEL_ROUTING") is not None:
        return _truthy(os.environ.get("KERROS_CHANNEL_ROUTING"))
    return True


def _slug(part: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._+-]+", "-", (part or "").strip())[:48]
    return s or "anon"


def route_key(channel: str, chat_id: str = "", sender: str = "") -> str:
    return f"{_slug(channel)}|{_slug(chat_id)}|{_slug(sender)}"


def session_id_for(
    channel: str,
    chat_id: str = "",
    sender: str = "",
    *,
    force: bool = False,
) -> str:
    """
    Stable session id for a channel conversation.

    Format: ch-<channel>-<short_hash> (readable + collision-resistant).
    """
    if not routing_enabled() and not force:
        try:
            from memory.session_store import get_current_session_id

            return get_current_session_id()
        except Exception:
            pass
    key = route_key(channel, chat_id, sender)
    with _lock:
        if key in _cache:
            return _cache[key]
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
        sid = f"ch-{_slug(channel)}-{digest}"
        _cache[key] = sid
        return sid


def clear_route_cache() -> None:
    with _lock:
        _cache.clear()


def index_channel_turn(
    role: str,
    content: str,
    *,
    channel: str,
    chat_id: str = "",
    sender: str = "",
) -> Optional[str]:
    """Index a turn into the routed session; returns session_id or None."""
    try:
        from memory.session_store import index_turn, start_session
    except Exception:
        return None
    sid = session_id_for(channel, chat_id, sender)
    try:
        start_session(sid)
        index_turn(
            role,
            content,
            session_id=sid,
            source=f"channel:{channel}",
        )
    except Exception:
        return sid
    return sid
