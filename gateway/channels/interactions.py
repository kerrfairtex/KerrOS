"""
gateway/channels/interactions.py
================================
Soft Discord Interactions HTTP helpers (ADR-084).

Soft signature verify for CI (HMAC-SHA256 over timestamp+body using
KERROS_DISCORD_PUBLIC_KEY as key). Live Ed25519 can be added when a crypto
dependency is available; Soft remains default.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Mapping, Optional


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def soft_interactions_enabled() -> bool:
    if os.environ.get("KERROS_DISCORD_INTERACTIONS_SOFT") is not None:
        return _truthy(os.environ.get("KERROS_DISCORD_INTERACTIONS_SOFT"))
    return True


def soft_sign(timestamp: str, body: bytes, *, key: Optional[str] = None) -> str:
    secret = (key or os.environ.get("KERROS_DISCORD_PUBLIC_KEY") or "kerros-soft").encode(
        "utf-8"
    )
    msg = (timestamp or "").encode("utf-8") + (body or b"")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify_interaction_request(
    headers: Mapping[str, str],
    body: bytes,
) -> dict[str, Any]:
    """
    Verify Soft (or passthrough) interaction signature.

    Soft headers:
      X-Signature-Timestamp
      X-Signature-Ed25519  (Soft HMAC hex when KERROS_DISCORD_INTERACTIONS_SOFT=1)
    """
    # Normalize header access
    def _h(name: str) -> str:
        for k, v in headers.items():
            if k.lower() == name.lower():
                return str(v)
        return ""

    ts = _h("X-Signature-Timestamp") or _h("x-signature-timestamp")
    sig = _h("X-Signature-Ed25519") or _h("x-signature-ed25519")
    if soft_interactions_enabled():
        if _truthy(_h("X-Kerros-Soft-Sign")) and not sig:
            # Explicit Soft bypass for local demos
            return {"ok": True, "mode": "soft-bypass"}
        if not ts or not sig:
            return {"ok": False, "error": "missing Soft signature headers", "mode": "soft"}
        expect = soft_sign(ts, body)
        if hmac.compare_digest(expect, sig.lower()):
            return {"ok": True, "mode": "soft-hmac"}
        return {"ok": False, "error": "invalid Soft signature", "mode": "soft"}
    # Non-Soft: require soft still unless crypto available (kept Soft-safe)
    return {
        "ok": False,
        "error": "live Ed25519 verify not configured — enable Soft or install crypto",
        "mode": "unset",
    }


def handle_interactions_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Discord-shaped Soft interaction payload → response body."""
    if not isinstance(payload, dict):
        return {"type": 4, "data": {"content": "invalid payload"}}
    # PING
    if int(payload.get("type") or 0) == 1:
        return {"type": 1}
    # APPLICATION_COMMAND
    if int(payload.get("type") or 0) == 2:
        from gateway.channels.slash import soft_interaction_create

        result = soft_interaction_create(payload)
        content = str(result.get("content") or "ok")[:2000]
        return {"type": 4, "data": {"content": content}, "kerros": result}
    return {"type": 4, "data": {"content": "unsupported Soft interaction type"}}
