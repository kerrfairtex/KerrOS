"""
gateway/channels/rate_limit.py
==============================
Soft per-channel rate limits (ADR-095) + file-backed shared store (ADR-098).

Token-bucket-ish sliding window. Default: 30 messages / 60s per
channel+chat_id+sender key. Configure with KERROS_CHANNEL_RATE=30/60.

When KERROS_CHANNEL_RATE_SHARED=1, hits persist under
data/channel_rate.json so multiple processes Soft-share limits.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

_lock = threading.RLock()
_hits: Dict[str, List[float]] = {}
BASE = Path(os.path.expanduser("~/offline_ai"))
STORE = BASE / "data" / "channel_rate.json"


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def shared_enabled() -> bool:
    return _truthy(os.environ.get("KERROS_CHANNEL_RATE_SHARED"))


def _parse_limit() -> Tuple[int, float]:
    raw = (os.environ.get("KERROS_CHANNEL_RATE") or "30/60").strip()
    try:
        count_s, window_s = raw.split("/", 1)
        return max(1, int(count_s)), max(1.0, float(window_s))
    except Exception:
        return 30, 60.0


def rate_key(channel: str, chat_id: str = "", sender: str = "") -> str:
    return f"{channel}|{chat_id}|{sender}"


def _load_shared() -> Dict[str, List[float]]:
    if not STORE.exists():
        return {}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out: Dict[str, List[float]] = {}
            for k, v in data.items():
                if isinstance(v, list):
                    out[str(k)] = [float(x) for x in v if isinstance(x, (int, float))]
            return out
    except Exception:
        pass
    return {}


def _save_shared(hits: Dict[str, List[float]]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(hits), encoding="utf-8")


def allow(channel: str, chat_id: str = "", sender: str = "") -> dict[str, Any]:
    limit, window = _parse_limit()
    key = rate_key(channel, chat_id, sender)
    now = time.time()
    with _lock:
        if shared_enabled():
            hits = _load_shared()
        else:
            hits = _hits
        bucket = hits.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            result = {
                "ok": False,
                "allowed": False,
                "limit": limit,
                "window": window,
                "shared": shared_enabled(),
                "retry_after": max(0.0, window - (now - bucket[0])) if bucket else window,
            }
            if shared_enabled():
                _save_shared(hits)
            return result
        bucket.append(now)
        if shared_enabled():
            _save_shared(hits)
        else:
            _hits[key] = bucket
        return {
            "ok": True,
            "allowed": True,
            "limit": limit,
            "window": window,
            "shared": shared_enabled(),
            "remaining": limit - len(bucket),
        }


def reset_limits() -> None:
    with _lock:
        _hits.clear()
        if STORE.exists():
            try:
                STORE.write_text("{}", encoding="utf-8")
            except Exception:
                pass
