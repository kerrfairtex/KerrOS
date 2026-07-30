"""
adapters/auth/idp_portal.py
===========================
IdP / data-subject portal foundation (ADR-034).

Default-off. Soft OIDC discovery probe + local portal sessions that map
access/erasure requests onto the existing erasure ledger APIs without
implementing a full OIDC RP. Fake IdP for CI.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class IdpPortalError(RuntimeError):
    """IdP / portal operation failed."""


ErasureHook = Callable[[str, str], dict[str, Any]]


def soft_oidc_discovery(
    issuer: str, *, timeout_s: float = 5.0
) -> dict[str, Any]:
    """Soft GET of ``{issuer}/.well-known/openid-configuration``."""
    base = str(issuer or "").rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "error": "issuer required"}
    url = f"{base}/.well-known/openid-configuration"
    try:
        req = Request(url, method="GET", headers={"User-Agent": "kerros-idp/1"})
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "ok": True,
            "issuer": data.get("issuer") if isinstance(data, dict) else base,
            "authorization_endpoint": (
                data.get("authorization_endpoint") if isinstance(data, dict) else None
            ),
            "token_endpoint": (
                data.get("token_endpoint") if isinstance(data, dict) else None
            ),
            "keys": sorted(data.keys()) if isinstance(data, dict) else [],
        }
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc), "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "url": url}


@dataclass
class FakeOidcIdp:
    """In-memory IdP that issues opaque portal tokens."""

    issuer: str = "https://idp.test"
    _users: dict[str, dict[str, Any]] = field(default_factory=dict)
    _tokens: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def register_subject(self, subject_id: str, *, email: str = "") -> dict[str, Any]:
        sid = str(subject_id or "").strip()
        if not sid:
            raise IdpPortalError("subject_id required")
        with self._lock:
            self._users[sid] = {"subject_id": sid, "email": email, "issuer": self.issuer}
        return dict(self._users[sid])

    def issue_token(self, subject_id: str, *, scopes: Optional[list[str]] = None) -> str:
        sid = str(subject_id or "").strip()
        if sid not in self._users:
            self.register_subject(sid)
        token = f"portal.{secrets.token_urlsafe(16)}"
        with self._lock:
            self._tokens[token] = {
                "subject_id": sid,
                "scopes": list(scopes or ["openid", "erasure.request", "access.request"]),
                "issued_at": time.time(),
            }
        return token

    def introspect(self, token: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._tokens[token]) if token in self._tokens else None

    def discovery(self) -> dict[str, Any]:
        return {
            "ok": True,
            "issuer": self.issuer,
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "keys": ["issuer", "authorization_endpoint", "token_endpoint"],
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "fake",
                "users": len(self._users),
                "tokens": len(self._tokens),
                "issuer": self.issuer,
            }


@dataclass
class IdpPortalConfig:
    enabled: bool = False
    issuer: str = ""
    allow_discovery_probe: bool = False
    backend: str = "fake"  # fake | oidc_probe
    session_ttl_s: float = 3600.0

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "IdpPortalConfig":
        data = dict(raw or {})
        nested = data.get("idp_portal") if isinstance(data.get("idp_portal"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_IDP_PORTAL")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        issuer = os.environ.get("KERROS_IDP_ISSUER")
        if issuer is None:
            issuer = str(nested.get("issuer") or "")

        probe = nested.get("allow_discovery_probe", False)
        env_p = os.environ.get("KERROS_IDP_DISCOVERY_PROBE")
        if env_p is not None:
            probe = _truthy(env_p)
        else:
            probe = _truthy(probe)

        backend = os.environ.get("KERROS_IDP_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        ttl = nested.get("session_ttl_s", 3600.0)
        env_t = os.environ.get("KERROS_IDP_SESSION_TTL")
        if env_t is not None:
            ttl = float(env_t)

        return cls(
            enabled=bool(enabled),
            issuer=str(issuer or "").strip(),
            allow_discovery_probe=bool(probe),
            backend=str(backend or "fake").strip().lower() or "fake",
            session_ttl_s=max(60.0, float(ttl or 3600.0)),
        )


@dataclass
class DataSubjectPortal:
    """
    Local portal facade: authenticate via Fake IdP token, then submit
    access/erasure intents (erasure via optional hook into ADR-025 ledger).
    """

    cfg: IdpPortalConfig
    idp: FakeOidcIdp = field(default_factory=FakeOidcIdp)
    erasure_hook: ErasureHook | None = None
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _requests: list[dict[str, Any]] = field(default_factory=list)
    _last_discovery: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def maybe_discover(self) -> dict[str, Any]:
        if not self.cfg.allow_discovery_probe:
            out = {"ok": False, "skipped": True, "error": "discovery probe disabled"}
            self._last_discovery = out
            return out
        if self.cfg.backend == "fake" or not self.cfg.issuer:
            out = self.idp.discovery()
            self._last_discovery = dict(out)
            return out
        out = soft_oidc_discovery(self.cfg.issuer)
        self._last_discovery = dict(out)
        return out

    def login(self, subject_id: str, *, email: str = "") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise IdpPortalError("IdP portal disabled")
        self.idp.register_subject(subject_id, email=email)
        token = self.idp.issue_token(subject_id)
        session_id = uuid.uuid4().hex
        with self._lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "subject_id": subject_id,
                "token": token,
                "expires_at": time.time() + self.cfg.session_ttl_s,
            }
        return {
            "session_id": session_id,
            "subject_id": subject_id,
            "token": token,
            "expires_in": self.cfg.session_ttl_s,
        }

    def _require_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            sess = self._sessions.get(str(session_id or ""))
            if not sess:
                raise IdpPortalError("invalid session")
            if float(sess.get("expires_at") or 0) < time.time():
                raise IdpPortalError("session expired")
            return dict(sess)

    def request_access(self, session_id: str) -> dict[str, Any]:
        sess = self._require_session(session_id)
        rec = {
            "id": uuid.uuid4().hex,
            "type": "access",
            "subject_id": sess["subject_id"],
            "status": "recorded",
            "at": time.time(),
        }
        with self._lock:
            self._requests.append(rec)
        return dict(rec)

    def request_erasure(self, session_id: str, *, reason: str = "") -> dict[str, Any]:
        sess = self._require_session(session_id)
        subject = sess["subject_id"]
        ledger_out: dict[str, Any] | None = None
        if self.erasure_hook is not None:
            try:
                ledger_out = self.erasure_hook(subject, reason)
            except Exception as exc:
                ledger_out = {"ok": False, "error": str(exc)}
        rec = {
            "id": uuid.uuid4().hex,
            "type": "erasure",
            "subject_id": subject,
            "status": "recorded",
            "reason": reason,
            "at": time.time(),
            "ledger": ledger_out,
        }
        with self._lock:
            self._requests.append(rec)
        return dict(rec)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "issuer": self.cfg.issuer or self.idp.issuer,
                "sessions": len(self._sessions),
                "requests": len(self._requests),
                "last_discovery": dict(self._last_discovery),
                "idp": self.idp.stats(),
            }


def build_idp_portal(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    erasure_hook: ErasureHook | None = None,
    idp: FakeOidcIdp | None = None,
) -> DataSubjectPortal | None:
    portal_cfg = IdpPortalConfig.from_mapping(cfg)
    if not portal_cfg.enabled:
        return None
    fake = idp or FakeOidcIdp(
        issuer=portal_cfg.issuer or "https://idp.test"
    )
    return DataSubjectPortal(
        cfg=portal_cfg, idp=fake, erasure_hook=erasure_hook
    )
