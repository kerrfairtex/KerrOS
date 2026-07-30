"""
adapters/auth/oidc_rp.py
========================
Full OIDC *relying party* foundation (ADR-036).

Default-off. Implements authorization-code flow plumbing with a Fake IdP
for CI and soft HTTP token exchange when ``allow_live``. Does not hard-
require Authlib — optional soft import for discovery helpers only.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from adapters.auth.idp_portal import FakeOidcIdp, soft_oidc_discovery


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class OidcRpError(RuntimeError):
    """OIDC RP operation failed."""


def authlib_available() -> bool:
    try:
        import authlib  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class OidcRpConfig:
    enabled: bool = False
    client_id: str = "kerros"
    client_secret: str = ""
    redirect_uri: str = "http://127.0.0.1:8080/oidc/callback"
    issuer: str = "https://idp.test"
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    allow_live: bool = False
    allow_discovery_probe: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "OidcRpConfig":
        data = dict(raw or {})
        nested = data.get("oidc_rp") if isinstance(data.get("oidc_rp"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_OIDC_RP")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        client_id = os.environ.get("KERROS_OIDC_CLIENT_ID")
        if client_id is None:
            client_id = str(nested.get("client_id") or "kerros")

        secret = os.environ.get("KERROS_OIDC_CLIENT_SECRET")
        if secret is None:
            secret = str(nested.get("client_secret") or "")

        redirect = os.environ.get("KERROS_OIDC_REDIRECT_URI")
        if redirect is None:
            redirect = str(
                nested.get("redirect_uri") or "http://127.0.0.1:8080/oidc/callback"
            )

        issuer = os.environ.get("KERROS_OIDC_ISSUER")
        if issuer is None:
            issuer = str(nested.get("issuer") or "https://idp.test")

        scopes_raw = nested.get("scopes") or ["openid", "profile", "email"]
        env_sc = os.environ.get("KERROS_OIDC_SCOPES")
        if env_sc is not None:
            scopes = [s.strip() for s in env_sc.split() if s.strip()]
        elif isinstance(scopes_raw, str):
            scopes = [s.strip() for s in scopes_raw.split() if s.strip()]
        else:
            scopes = [str(s).strip() for s in scopes_raw if str(s).strip()]

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_OIDC_RP_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        probe = nested.get("allow_discovery_probe", False)
        env_p = os.environ.get("KERROS_OIDC_RP_DISCOVERY")
        if env_p is not None:
            probe = _truthy(env_p)
        else:
            probe = _truthy(probe)

        return cls(
            enabled=bool(enabled),
            client_id=str(client_id or "kerros").strip() or "kerros",
            client_secret=str(secret or "").strip(),
            redirect_uri=str(redirect or "").strip(),
            issuer=str(issuer or "https://idp.test").strip() or "https://idp.test",
            scopes=scopes or ["openid"],
            allow_live=bool(allow_live),
            allow_discovery_probe=bool(probe),
        )


@dataclass
class OidcRelyingParty:
    """Authorization-code RP with Fake IdP support."""

    cfg: OidcRpConfig
    idp: FakeOidcIdp = field(default_factory=FakeOidcIdp)
    _states: dict[str, dict[str, Any]] = field(default_factory=dict)
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _last_discovery: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def discover(self) -> dict[str, Any]:
        if not self.cfg.allow_discovery_probe:
            # Use fake discovery document.
            out = self.idp.discovery()
            self._last_discovery = dict(out)
            return out
        if self.cfg.allow_live and self.cfg.issuer and not self.cfg.issuer.endswith(".test"):
            out = soft_oidc_discovery(self.cfg.issuer)
        else:
            out = self.idp.discovery()
        self._last_discovery = dict(out)
        return out

    def begin_auth(self, *, subject_hint: str = "") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise OidcRpError("OIDC RP disabled")
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(12)
        code_verifier = secrets.token_urlsafe(32)
        challenge = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = (
            __import__("base64")
            .urlsafe_b64encode(challenge)
            .decode("ascii")
            .rstrip("=")
        )
        discovery = self.discover()
        auth_ep = str(
            discovery.get("authorization_endpoint")
            or f"{self.cfg.issuer}/authorize"
        )
        params = {
            "response_type": "code",
            "client_id": self.cfg.client_id,
            "redirect_uri": self.cfg.redirect_uri,
            "scope": " ".join(self.cfg.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if subject_hint:
            params["login_hint"] = subject_hint
        url = f"{auth_ep}?{urlencode(params)}"
        with self._lock:
            self._states[state] = {
                "nonce": nonce,
                "code_verifier": code_verifier,
                "subject_hint": subject_hint,
                "created_at": time.time(),
            }
        return {"authorization_url": url, "state": state, "nonce": nonce}

    def complete_auth(
        self, *, state: str, code: str = "", subject_id: str = ""
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise OidcRpError("OIDC RP disabled")
        with self._lock:
            pending = self._states.pop(str(state or ""), None)
        if not pending:
            raise OidcRpError("unknown or expired state")

        # Fake path: mint tokens locally (default). Live token endpoint soft.
        sid = str(subject_id or pending.get("subject_hint") or "user").strip() or "user"
        if self.cfg.allow_live and code and not code.startswith("fake."):
            token_out = self._live_token_exchange(code, pending["code_verifier"])
            if not token_out.get("ok"):
                return token_out
            access = str(token_out.get("access_token") or "")
            id_token = str(token_out.get("id_token") or "")
        else:
            self.idp.register_subject(sid)
            access = self.idp.issue_token(sid, scopes=list(self.cfg.scopes))
            id_token = f"fake-id-token.{sid}.{pending['nonce']}"
            # Consume authorization code if provided by fake IdP pattern.
            _ = code or f"fake.{uuid.uuid4().hex}"

        session_id = uuid.uuid4().hex
        session = {
            "session_id": session_id,
            "subject_id": sid,
            "access_token": access,
            "id_token": id_token,
            "nonce": pending["nonce"],
            "authenticated_at": time.time(),
        }
        with self._lock:
            self._sessions[session_id] = dict(session)
        return {"ok": True, **session}

    def _live_token_exchange(self, code: str, code_verifier: str) -> dict[str, Any]:
        discovery = self._last_discovery or self.discover()
        token_ep = str(discovery.get("token_endpoint") or "")
        if not token_ep:
            return {"ok": False, "error": "token_endpoint missing"}
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.cfg.redirect_uri,
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "code_verifier": code_verifier,
            }
        ).encode("utf-8")
        try:
            req = Request(
                token_ep,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "kerros-oidc-rp/1",
                },
            )
            with urlopen(req, timeout=5.0) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, **(data if isinstance(data, dict) else {})}
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc)}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._sessions[session_id]) if session_id in self._sessions else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "client_id": self.cfg.client_id,
                "issuer": self.cfg.issuer,
                "allow_live": self.cfg.allow_live,
                "pending_states": len(self._states),
                "sessions": len(self._sessions),
                "authlib": authlib_available(),
                "last_discovery": dict(self._last_discovery),
            }


def build_oidc_rp(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    idp: FakeOidcIdp | None = None,
) -> OidcRelyingParty | None:
    rp_cfg = OidcRpConfig.from_mapping(cfg)
    if not rp_cfg.enabled:
        return None
    fake = idp or FakeOidcIdp(issuer=rp_cfg.issuer)
    return OidcRelyingParty(cfg=rp_cfg, idp=fake)
