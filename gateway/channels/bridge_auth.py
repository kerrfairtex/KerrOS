"""
gateway/channels/bridge_auth.py
===============================
Soft signed per-bridge credentials (ADR-100).

Bridges present:
  X-Kerros-Bridge-Id
  X-Kerros-Bridge-Ts
  X-Kerros-Bridge-Sign  = HMAC-SHA256(secret, id|ts|body)

Secrets map via KERROS_BRIDGE_SECRETS JSON:
  {"signal-1":"secretA","discord-bridge":"secretB"}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Mapping


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def bridge_auth_required() -> bool:
    return _truthy(os.environ.get("KERROS_BRIDGE_AUTH"))


def load_secrets() -> dict[str, str]:
    raw = (os.environ.get("KERROS_BRIDGE_SECRETS") or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def sign_bridge(bridge_id: str, ts: str, body: bytes, secret: str) -> str:
    msg = f"{bridge_id}|{ts}|".encode("utf-8") + (body or b"")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def verify_bridge_request(headers: Mapping[str, str], body: bytes) -> dict[str, Any]:
    if not bridge_auth_required():
        return {"ok": True, "mode": "open"}

    def _h(name: str) -> str:
        for k, v in headers.items():
            if k.lower() == name.lower():
                return str(v)
        return ""

    bridge_id = _h("X-Kerros-Bridge-Id")
    ts = _h("X-Kerros-Bridge-Ts")
    sig = _h("X-Kerros-Bridge-Sign")
    if not bridge_id or not ts or not sig:
        return {"ok": False, "error": "missing bridge auth headers", "mode": "bridge"}
    try:
        ts_i = int(ts)
    except Exception:
        return {"ok": False, "error": "invalid bridge timestamp", "mode": "bridge"}
    # 5 minute skew Soft window
    if abs(int(time.time()) - ts_i) > 300:
        return {"ok": False, "error": "bridge timestamp skew", "mode": "bridge"}
    secrets = load_secrets()
    secret = secrets.get(bridge_id)
    if not secret:
        return {"ok": False, "error": f"unknown bridge id: {bridge_id}", "mode": "bridge"}
    expect = sign_bridge(bridge_id, ts, body, secret)
    if not hmac.compare_digest(expect, sig.lower()):
        return {"ok": False, "error": "invalid bridge signature", "mode": "bridge"}
    return {"ok": True, "mode": "bridge", "bridge_id": bridge_id}
