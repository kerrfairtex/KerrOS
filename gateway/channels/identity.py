"""
gateway/channels/identity.py
============================
Cross-channel Soft identity linking (ADR-088).

Maps aliases like telegram:alice ↔ discord:bob → one KerrOS identity id so
session routing can optionally share memory across platforms.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

_lock = threading.RLock()
BASE = Path(os.path.expanduser("~/offline_ai"))
STORE = BASE / "data" / "channel_identities.json"


def _path() -> Path:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    return STORE


def _load() -> dict[str, Any]:
    p = _path()
    if not p.exists():
        return {"identities": {}, "aliases": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("identities", {})
            data.setdefault("aliases", {})
            return data
    except Exception:
        pass
    return {"identities": {}, "aliases": {}}


def _save(data: dict[str, Any]) -> None:
    _path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def alias_key(channel: str, sender: str) -> str:
    return f"{(channel or '').strip().lower()}:{(sender or '').strip().lower()}"


def link_identity(
    channel: str,
    sender: str,
    *,
    identity_id: Optional[str] = None,
    label: str = "",
) -> dict[str, Any]:
    key = alias_key(channel, sender)
    with _lock:
        data = _load()
        existing = data["aliases"].get(key)
        if existing and not identity_id:
            return {"ok": True, "identity_id": existing, "alias": key, "existing": True}
        iid = identity_id or existing or ("id-" + uuid.uuid4().hex[:10])
        data["aliases"][key] = iid
        meta = data["identities"].setdefault(iid, {"label": label or iid, "aliases": []})
        if label:
            meta["label"] = label
        if key not in meta["aliases"]:
            meta["aliases"].append(key)
        _save(data)
        return {"ok": True, "identity_id": iid, "alias": key, "existing": bool(existing)}


def resolve_identity(channel: str, sender: str) -> Optional[str]:
    key = alias_key(channel, sender)
    with _lock:
        return _load()["aliases"].get(key)


def list_identities() -> dict[str, Any]:
    with _lock:
        return {"ok": True, **_load()}


def unlink_alias(channel: str, sender: str) -> dict[str, Any]:
    key = alias_key(channel, sender)
    with _lock:
        data = _load()
        iid = data["aliases"].pop(key, None)
        if iid and iid in data["identities"]:
            aliases = data["identities"][iid].get("aliases") or []
            data["identities"][iid]["aliases"] = [a for a in aliases if a != key]
            if not data["identities"][iid]["aliases"]:
                data["identities"].pop(iid, None)
        _save(data)
        return {"ok": True, "removed": key, "identity_id": iid}


def routed_sender(channel: str, sender: str) -> str:
    """
    When linked, return identity_id for session routing stability across channels.
    """
    iid = resolve_identity(channel, sender)
    return iid or sender
