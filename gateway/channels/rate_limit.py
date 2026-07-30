"""
gateway/channels/rate_limit.py
==============================
Soft per-channel rate limits (ADR-095).

Token-bucket-ish sliding window in memory. Default: 30 messages / 60s per
channel+chat_id key. Configure with KERROS_CHANNEL_RATE=30/60.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Tuple

_lock = threading.RLock()
_hits: Dict[str, List[float]] = {}


def _parse_limit() -> Tuple[int, float]:
    raw = (os.environ.get("KERROS_CHANNEL_RATE") or "30/60").strip()
    try:
        count_s, window_s = raw.split("/", 1)
        return max(1, int(count_s)), max(1.0, float(window_s))
    except Exception:
        return 30, 60.0


def rate_key(channel: str, chat_id: str = "", sender: str = "") -> str:
    return f"{channel}|{chat_id}|{sender}"


def allow(channel: str, chat_id: str = "", sender: str = "") -> dict[str, Any]:
    limit, window = _parse_limit()
    key = rate_key(channel, chat_id, sender)
    now = time.time()
    with _lock:
        bucket = _hits.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return {
                "ok": False,
                "allowed": False,
                "limit": limit,
                "window": window,
                "retry_after": max(0.0, window - (now - bucket[0])),
            }
        bucket.append(now)
        return {
            "ok": True,
            "allowed": True,
            "limit": limit,
            "window": window,
            "remaining": limit - len(bucket),
        }


def reset_limits() -> None:
    with _lock:
        _hits.clear()
