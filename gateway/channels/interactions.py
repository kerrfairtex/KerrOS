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


def _verify_ed25519(timestamp: str, body: bytes, signature_hex: str) -> dict[str, Any]:
    """
    ADR-092: optional live Ed25519 verify when PyNaCl is installed and Soft is off.
    Public key is hex in KERROS_DISCORD_PUBLIC_KEY.
    """
    pub_hex = (os.environ.get("KERROS_DISCORD_PUBLIC_KEY") or "").strip()
    if not pub_hex:
        return {"ok": False, "error": "missing KERROS_DISCORD_PUBLIC_KEY", "mode": "ed25519"}
    try:
        from nacl.exceptions import BadSignatureError  # type: ignore
        from nacl.signing import VerifyKey  # type: ignore
    except Exception:
        return {
            "ok": False,
            "error": "PyNaCl not installed — Soft HMAC or pip install pynacl",
            "mode": "ed25519-missing",
        }
    try:
        key = VerifyKey(bytes.fromhex(pub_hex))
        msg = (timestamp or "").encode("utf-8") + (body or b"")
        key.verify(msg, bytes.fromhex(signature_hex))
        return {"ok": True, "mode": "ed25519"}
    except BadSignatureError:
        return {"ok": False, "error": "invalid Ed25519 signature", "mode": "ed25519"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "mode": "ed25519"}


def verify_interaction_request(
    headers: Mapping[str, str],
    body: bytes,
) -> dict[str, Any]:
    """
    Verify Soft HMAC or optional live Ed25519 (ADR-084 / ADR-092).

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
    if not ts or not sig:
        return {"ok": False, "error": "missing signature headers", "mode": "ed25519"}
    return _verify_ed25519(ts, body, sig)


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
