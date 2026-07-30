"""
adapters/auth/saml_sp.py
========================
SAML 2.0 Service Provider foundation (ADR-041).

Default-off. Fake IdP + soft ACS/SSO plumbing for CI. Does not hard-
require pysaml2 / python3-saml — optional soft import only.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import urlencode


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class SamlSpError(RuntimeError):
    """SAML SP operation failed."""


def pysaml2_available() -> bool:
    try:
        import saml2  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class FakeSamlIdp:
    """Minimal Fake SAML IdP for ACS testing."""

    entity_id: str = "https://idp.test/saml"
    _assertions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def issue_assertion(
        self,
        *,
        name_id: str,
        audience: str,
        attributes: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        assertion_id = f"_a{uuid.uuid4().hex[:16]}"
        doc = {
            "id": assertion_id,
            "issuer": self.entity_id,
            "name_id": str(name_id).strip(),
            "audience": str(audience).strip(),
            "attributes": dict(attributes or {"email": f"{name_id}@test.local"}),
            "issued_at": time.time(),
            "not_on_or_after": time.time() + 300,
        }
        # Simulate base64 SAMLResponse
        raw = (
            f"<Assertion ID='{assertion_id}' Issuer='{self.entity_id}' "
            f"NameID='{doc['name_id']}' Audience='{doc['audience']}'/>"
        ).encode("utf-8")
        doc["saml_response_b64"] = base64.b64encode(raw).decode("ascii")
        with self._lock:
            self._assertions[assertion_id] = dict(doc)
        return doc

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake_idp", "assertions": len(self._assertions)}


@dataclass
class SamlSpConfig:
    enabled: bool = False
    entity_id: str = "https://kerros.local/saml/sp"
    acs_url: str = "http://127.0.0.1:8080/saml/acs"
    idp_entity_id: str = "https://idp.test/saml"
    idp_sso_url: str = "https://idp.test/saml/sso"
    allow_live: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "SamlSpConfig":
        data = dict(raw or {})
        nested = data.get("saml_sp") if isinstance(data.get("saml_sp"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_SAML_SP")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        entity_id = os.environ.get("KERROS_SAML_ENTITY_ID")
        if entity_id is None:
            entity_id = str(nested.get("entity_id") or "https://kerros.local/saml/sp")

        acs = os.environ.get("KERROS_SAML_ACS_URL")
        if acs is None:
            acs = str(nested.get("acs_url") or "http://127.0.0.1:8080/saml/acs")

        idp = os.environ.get("KERROS_SAML_IDP_ENTITY_ID")
        if idp is None:
            idp = str(nested.get("idp_entity_id") or "https://idp.test/saml")

        sso = os.environ.get("KERROS_SAML_IDP_SSO_URL")
        if sso is None:
            sso = str(nested.get("idp_sso_url") or "https://idp.test/saml/sso")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_SAML_SP_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        return cls(
            enabled=bool(enabled),
            entity_id=str(entity_id or "").strip(),
            acs_url=str(acs or "").strip(),
            idp_entity_id=str(idp or "").strip(),
            idp_sso_url=str(sso or "").strip(),
            allow_live=bool(allow_live),
        )


@dataclass
class SamlServiceProvider:
    """SAML SP authn request + ACS consume foundation."""

    cfg: SamlSpConfig
    idp: FakeSamlIdp = field(default_factory=FakeSamlIdp)
    _pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def metadata_xml(self) -> str:
        return (
            f'<EntityDescriptor entityID="{self.cfg.entity_id}">'
            f'<SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
            f'<AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
            f'Location="{self.cfg.acs_url}" index="0"/>'
            f"</SPSSODescriptor></EntityDescriptor>"
        )

    def begin_login(self, *, relay_state: str = "/") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SamlSpError("SAML SP disabled")
        req_id = f"_r{uuid.uuid4().hex[:16]}"
        # Minimal AuthnRequest XML (not signed)
        authn = (
            f"<AuthnRequest ID='{req_id}' Version='2.0' "
            f"IssueInstant='{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' "
            f"AssertionConsumerServiceURL='{self.cfg.acs_url}' "
            f"Destination='{self.cfg.idp_sso_url}'>"
            f"<Issuer>{self.cfg.entity_id}</Issuer>"
            f"</AuthnRequest>"
        )
        b64 = base64.b64encode(authn.encode("utf-8")).decode("ascii")
        with self._lock:
            self._pending[req_id] = {
                "id": req_id,
                "relay_state": relay_state,
                "created_at": time.time(),
            }
        redirect = (
            f"{self.cfg.idp_sso_url}?{urlencode({'SAMLRequest': b64, 'RelayState': relay_state})}"
        )
        return {
            "ok": True,
            "request_id": req_id,
            "redirect_url": redirect,
            "saml_request_b64": b64,
            "live": False,
            "note": "Fake SSO redirect — not a live IdP binding",
        }

    def consume(
        self,
        *,
        saml_response_b64: Optional[str] = None,
        name_id: Optional[str] = None,
        request_id: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """Consume ACS — Fake path issues assertion when no response provided."""
        if not self.cfg.enabled:
            raise SamlSpError("SAML SP disabled")
        if self.cfg.allow_live and saml_response_b64:
            # Soft live: decode and accept presence only (no full XML crypto)
            try:
                raw = base64.b64decode(saml_response_b64.encode("ascii"), validate=False)
            except Exception as exc:
                raise SamlSpError(f"invalid SAMLResponse: {exc}") from exc
            session_id = secrets.token_urlsafe(16)
            session = {
                "session_id": session_id,
                "name_id": name_id or "live-user",
                "attributes": dict(attributes or {}),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "backend": "live_soft",
                "at": time.time(),
            }
        else:
            assertion = self.idp.issue_assertion(
                name_id=name_id or "demo-user",
                audience=self.cfg.entity_id,
                attributes=attributes,
            )
            session_id = secrets.token_urlsafe(16)
            session = {
                "session_id": session_id,
                "name_id": assertion["name_id"],
                "attributes": dict(assertion["attributes"]),
                "assertion_id": assertion["id"],
                "backend": "fake",
                "at": time.time(),
            }
            saml_response_b64 = assertion["saml_response_b64"]
        with self._lock:
            if request_id and request_id in self._pending:
                del self._pending[request_id]
            self._sessions[session_id] = dict(session)
        return {
            "ok": True,
            "session": session,
            "saml_response_b64": saml_response_b64,
            "certification": False,
        }

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(session_id)
            return dict(s) if s else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "entity_id": self.cfg.entity_id,
                "acs_url": self.cfg.acs_url,
                "allow_live": self.cfg.allow_live,
                "pending": len(self._pending),
                "sessions": len(self._sessions),
                "pysaml2": pysaml2_available(),
                "idp": self.idp.stats(),
            }


def build_saml_sp(
    cfg: Optional[Mapping[str, Any] | SamlSpConfig] = None,
) -> Optional[SamlServiceProvider]:
    if isinstance(cfg, SamlSpConfig):
        resolved = cfg
    else:
        resolved = SamlSpConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None
    idp = FakeSamlIdp(entity_id=resolved.idp_entity_id)
    return SamlServiceProvider(cfg=resolved, idp=idp)
