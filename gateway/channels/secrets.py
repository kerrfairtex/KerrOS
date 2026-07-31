"""
gateway/channels/secrets.py
===========================
Soft secrets vault file (ADR-103).

Stores non-production Soft secrets under data/channel_secrets.json
(chmod-best-effort). Used to resolve KERROS_* placeholders and bridge
secrets without putting everything in the process environment.
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()
BASE = Path(os.path.expanduser("~/offline_ai"))
VAULT = BASE / "data" / "channel_secrets.json"


def _path() -> Path:
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    return VAULT


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {"secrets": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("secrets", {})
            return data
    except Exception:
        pass
    return {"secrets": {}}


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def set_secret(name: str, value: str) -> dict[str, Any]:
    key = (name or "").strip()
    if not key:
        return {"ok": False, "error": "name required"}
    with _lock:
        data = _load()
        data["secrets"][key] = str(value)
        _save(data)
    return {"ok": True, "name": key, "set": True}


def get_secret(name: str, default: str = "") -> str:
    key = (name or "").strip()
    with _lock:
        val = (_load().get("secrets") or {}).get(key)
    if val is None or val == "":
        return os.environ.get(key, default)
    return str(val)


def list_secrets() -> dict[str, Any]:
    with _lock:
        keys = sorted((_load().get("secrets") or {}).keys())
    return {"ok": True, "names": keys, "count": len(keys)}


def delete_secret(name: str) -> dict[str, Any]:
    key = (name or "").strip()
    with _lock:
        data = _load()
        existed = key in (data.get("secrets") or {})
        (data.get("secrets") or {}).pop(key, None)
        _save(data)
    return {"ok": True, "deleted": existed, "name": key}


def apply_vault_to_environ(*, keys: Optional[list[str]] = None) -> dict[str, Any]:
    """Soft-export vault secrets into os.environ when missing."""
    applied = []
    with _lock:
        secrets = _load().get("secrets") or {}
        for k, v in secrets.items():
            if keys and k not in keys:
                continue
            if not os.environ.get(k):
                os.environ[k] = str(v)
                applied.append(k)
    return {"ok": True, "applied": applied}
