"""
runtime/mesh_auth.py
====================
Shared-secret authentication for KerrOS mesh transports (ADR-014).

Used by HTTP event-mesh ingest and actor-mesh envelopes. When ``token`` is
empty, auth is disabled (dev / loopback default). When set, peers must present
the same secret (constant-time compare).
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional


HEADER_AUTHORIZATION = "Authorization"
HEADER_MESH_TOKEN = "X-Kerros-Mesh-Token"
BEARER_PREFIX = "Bearer "


@dataclass(frozen=True)
class MeshAuth:
    """Mesh shared-secret settings."""

    token: str = ""
    # When True, refuse to start listeners / send if token is empty.
    required: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def ensure_ready(self, *, what: str = "mesh auth") -> None:
        if self.required and not self.token:
            raise RuntimeError(
                f"{what}: auth_required but no token configured "
                f"(set auth_token / KERROS_*_MESH_TOKEN)"
            )


def mesh_auth_from_config(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    env_token: str = "KERROS_EVENT_MESH_TOKEN",
    env_required: str = "KERROS_EVENT_MESH_AUTH_REQUIRED",
) -> MeshAuth:
    """Build MeshAuth from a config mapping + env overrides."""
    data = dict(cfg or {})
    token = os.environ.get(env_token)
    if token is None:
        token = str(data.get("auth_token") or data.get("token") or "")
    else:
        token = str(token)

    required_raw = os.environ.get(env_required)
    if required_raw is None:
        required_raw = data.get("auth_required", False)
    if isinstance(required_raw, str):
        required = required_raw.lower() in ("1", "true", "yes")
    else:
        required = bool(required_raw)

    # Configuring a token implies enforcement on protected endpoints.
    if token and not required:
        required = False  # token enables checks; required only blocks empty token
    return MeshAuth(token=token.strip(), required=bool(required))


def tokens_equal(expected: str, provided: str | None) -> bool:
    """Constant-time compare; empty expected means auth disabled → True."""
    if not expected:
        return True
    if provided is None:
        return False
    return hmac.compare_digest(
        expected.encode("utf-8"),
        str(provided).encode("utf-8"),
    )


def extract_http_token(headers: Mapping[str, str]) -> str | None:
    """Read Bearer or X-Kerros-Mesh-Token from HTTP headers (case-insensitive)."""
    # BaseHTTPRequestHandler headers are case-insensitive Message objects;
    # also accept plain dicts with mixed case.
    def _get(name: str) -> str | None:
        if hasattr(headers, "get"):
            # try exact then casefold scan
            val = headers.get(name)
            if val:
                return str(val)
            lower = name.lower()
            for key in headers:
                if str(key).lower() == lower:
                    return str(headers[key])
        return None

    auth = _get(HEADER_AUTHORIZATION)
    if auth:
        auth = auth.strip()
        if auth.lower().startswith(BEARER_PREFIX.lower()):
            return auth[len(BEARER_PREFIX) :].strip()
        return auth
    mesh = _get(HEADER_MESH_TOKEN)
    if mesh:
        return str(mesh).strip()
    return None


def check_http_auth(headers: Mapping[str, str], auth: MeshAuth) -> bool:
    """Return True if request is allowed under ``auth``."""
    if not auth.enabled:
        if auth.required:
            return False
        return True
    return tokens_equal(auth.token, extract_http_token(headers))


def http_auth_headers(auth: MeshAuth) -> dict[str, str]:
    """Outbound headers for authenticated mesh HTTP clients."""
    if not auth.enabled:
        return {}
    return {
        HEADER_AUTHORIZATION: f"{BEARER_PREFIX}{auth.token}",
        HEADER_MESH_TOKEN: auth.token,
    }


def wrap_actor_payload(raw_msg: dict[str, Any], auth: MeshAuth) -> dict[str, Any]:
    """Envelope actor message dict with optional token."""
    if not auth.enabled:
        return raw_msg
    return {"token": auth.token, "msg": raw_msg}


def unwrap_actor_payload(
    data: dict[str, Any], auth: MeshAuth
) -> dict[str, Any]:
    """Validate token envelope and return inner message dict.

    Accepts legacy unwrapped messages only when auth is disabled.
    """
    if "msg" in data and isinstance(data.get("msg"), dict):
        if auth.enabled and not tokens_equal(auth.token, data.get("token")):
            raise PermissionError("actor mesh auth failed")
        if auth.required and not auth.enabled:
            raise PermissionError("actor mesh auth required but not configured")
        return dict(data["msg"])
    # Legacy / unwrapped
    if auth.enabled:
        # Allow token field on the message itself
        if tokens_equal(auth.token, data.get("token")):
            out = dict(data)
            out.pop("token", None)
            return out
        raise PermissionError("actor mesh auth failed")
    return data
