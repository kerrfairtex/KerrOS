"""
adapters/auth/saml_federation.py
================================
Production SAML federation foundation (ADR-044).

Default-off. Multi-IdP federation catalog, Fake XML-signature
verification, soft encrypted-assertion stubs, and optional pysaml2 /
xmlsec probes. Does not hard-require pysaml2 — CI uses Fake crypto.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import urlencode

from adapters.auth.saml_sp import FakeSamlIdp, SamlSpError, pysaml2_available


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def xmlsec_available() -> bool:
    try:
        import xmlsec  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class IdpFederationEntry:
    """One federated IdP."""

    entity_id: str
    sso_url: str
    metadata_url: str = ""
    display_name: str = ""
    want_assertions_signed: bool = True
    want_assertions_encrypted: bool = False
    signing_cert_pem: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "sso_url": self.sso_url,
            "metadata_url": self.metadata_url,
            "display_name": self.display_name or self.entity_id,
            "want_assertions_signed": self.want_assertions_signed,
            "want_assertions_encrypted": self.want_assertions_encrypted,
            "has_signing_cert": bool(self.signing_cert_pem.strip()),
            "enabled": self.enabled,
        }


@dataclass
class FakeXmlSignature:
    """HMAC-based Fake XML signature for CI (not XMLDSig)."""

    key: bytes = b"kerros-saml-federation-fake-key"

    def sign(self, xml_bytes: bytes) -> dict[str, Any]:
        digest = hmac.new(self.key, xml_bytes, hashlib.sha256).hexdigest()
        return {
            "alg": "HMAC-SHA256-FAKE-XMLDSIG",
            "signature": digest,
            "payload_sha256": hashlib.sha256(xml_bytes).hexdigest(),
            "backend": "fake",
            "production": False,
        }

    def verify(self, xml_bytes: bytes, signature: Mapping[str, Any]) -> bool:
        expected = hmac.new(self.key, xml_bytes, hashlib.sha256).hexdigest()
        got = str(signature.get("signature") or "")
        return hmac.compare_digest(expected, got)


@dataclass
class SoftXmlsecVerifier:
    """Soft xmlsec/pysaml2 probe — shadows Fake when not allow_live."""

    allow_live: bool = False
    _shadow: FakeXmlSignature = field(default_factory=FakeXmlSignature)
    _last: dict[str, Any] = field(default_factory=dict)

    def sign(self, xml_bytes: bytes) -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.sign(xml_bytes)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        # Soft live: still Fake-sign unless xmlsec fully wired (foundation)
        out = self._shadow.sign(xml_bytes)
        out["backend"] = "soft_xmlsec"
        out["xmlsec"] = xmlsec_available()
        out["pysaml2"] = pysaml2_available()
        out["note"] = "soft live — full XMLDSig deferred to funded deploy"
        out["production"] = False
        self._last = dict(out)
        return out

    def verify(self, xml_bytes: bytes, signature: Mapping[str, Any]) -> bool:
        return self._shadow.verify(xml_bytes, signature)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "soft_xmlsec",
            "allow_live": self.allow_live,
            "xmlsec": xmlsec_available(),
            "pysaml2": pysaml2_available(),
            "last": dict(self._last),
        }


@dataclass
class SamlFederationConfig:
    enabled: bool = False
    entity_id: str = "https://kerros.local/saml/sp"
    acs_url: str = "http://127.0.0.1:8080/saml/acs"
    allow_live: bool = False
    require_signed_assertions: bool = True
    allow_encrypted_assertions: bool = False
    default_idp: str = ""

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "SamlFederationConfig":
        data = dict(raw or {})
        nested = (
            data.get("saml_federation")
            if isinstance(data.get("saml_federation"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_SAML_FEDERATION")
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

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_SAML_FEDERATION_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        require_signed = nested.get("require_signed_assertions", True)
        env_s = os.environ.get("KERROS_SAML_REQUIRE_SIGNED")
        if env_s is not None:
            require_signed = _truthy(env_s)
        else:
            require_signed = _truthy(require_signed)

        allow_enc = nested.get("allow_encrypted_assertions", False)
        env_e = os.environ.get("KERROS_SAML_ALLOW_ENCRYPTED")
        if env_e is not None:
            allow_enc = _truthy(env_e)
        else:
            allow_enc = _truthy(allow_enc)

        default_idp = os.environ.get("KERROS_SAML_DEFAULT_IDP")
        if default_idp is None:
            default_idp = str(nested.get("default_idp") or "")

        return cls(
            enabled=bool(enabled),
            entity_id=str(entity_id or "").strip(),
            acs_url=str(acs or "").strip(),
            allow_live=bool(allow_live),
            require_signed_assertions=bool(require_signed),
            allow_encrypted_assertions=bool(allow_enc),
            default_idp=str(default_idp or "").strip(),
        )


def _parse_idps(raw: Any) -> list[IdpFederationEntry]:
    entries: list[IdpFederationEntry] = []
    if not isinstance(raw, list):
        return entries
    for item in raw:
        if not isinstance(item, dict):
            continue
        entity = str(item.get("entity_id") or "").strip()
        sso = str(item.get("sso_url") or "").strip()
        if not entity or not sso:
            continue
        entries.append(
            IdpFederationEntry(
                entity_id=entity,
                sso_url=sso,
                metadata_url=str(item.get("metadata_url") or "").strip(),
                display_name=str(item.get("display_name") or "").strip(),
                want_assertions_signed=_truthy(
                    item.get("want_assertions_signed", True)
                ),
                want_assertions_encrypted=_truthy(
                    item.get("want_assertions_encrypted", False)
                ),
                signing_cert_pem=str(item.get("signing_cert_pem") or ""),
                enabled=_truthy(item.get("enabled", True)),
            )
        )
    return entries


@dataclass
class SamlFederation:
    """Multi-IdP SAML federation with Fake/soft XML crypto."""

    cfg: SamlFederationConfig
    idps: list[IdpFederationEntry] = field(default_factory=list)
    crypto: FakeXmlSignature | SoftXmlsecVerifier = field(
        default_factory=FakeXmlSignature
    )
    _pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    _sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def list_idps(self) -> list[dict[str, Any]]:
        with self._lock:
            return [i.to_dict() for i in self.idps if i.enabled]

    def get_idp(self, entity_id: str) -> Optional[IdpFederationEntry]:
        with self._lock:
            for idp in self.idps:
                if idp.entity_id == entity_id and idp.enabled:
                    return idp
        return None

    def register_idp(self, entry: IdpFederationEntry) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SamlSpError("SAML federation disabled")
        with self._lock:
            self.idps = [i for i in self.idps if i.entity_id != entry.entity_id]
            self.idps.append(entry)
        return {"ok": True, "entity_id": entry.entity_id}

    def metadata_xml(self) -> str:
        want_signed = "true" if self.cfg.require_signed_assertions else "false"
        return (
            f'<EntityDescriptor entityID="{self.cfg.entity_id}">'
            f'<SPSSODescriptor WantAssertionsSigned="{want_signed}" '
            f'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
            f'<AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
            f'Location="{self.cfg.acs_url}" index="0"/>'
            f"</SPSSODescriptor></EntityDescriptor>"
        )

    def begin_login(
        self,
        *,
        idp_entity_id: Optional[str] = None,
        relay_state: str = "/",
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SamlSpError("SAML federation disabled")
        target = idp_entity_id or self.cfg.default_idp
        idps = self.list_idps()
        if not target and idps:
            target = idps[0]["entity_id"]
        idp = self.get_idp(str(target or ""))
        if idp is None:
            raise SamlSpError(f"unknown or disabled IdP: {target}")
        req_id = f"_r{uuid.uuid4().hex[:16]}"
        authn = (
            f"<AuthnRequest ID='{req_id}' Version='2.0' "
            f"IssueInstant='{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}' "
            f"AssertionConsumerServiceURL='{self.cfg.acs_url}' "
            f"Destination='{idp.sso_url}'>"
            f"<Issuer>{self.cfg.entity_id}</Issuer>"
            f"</AuthnRequest>"
        ).encode("utf-8")
        sig = self.crypto.sign(authn)
        b64 = base64.b64encode(authn).decode("ascii")
        with self._lock:
            self._pending[req_id] = {
                "id": req_id,
                "idp": idp.entity_id,
                "relay_state": relay_state,
                "created_at": time.time(),
            }
        redirect = (
            f"{idp.sso_url}?{urlencode({'SAMLRequest': b64, 'RelayState': relay_state})}"
        )
        return {
            "ok": True,
            "request_id": req_id,
            "idp": idp.entity_id,
            "redirect_url": redirect,
            "request_signature": sig,
            "production": False,
            "note": "Federation AuthnRequest — Fake/soft signed",
        }

    def consume(
        self,
        *,
        idp_entity_id: Optional[str] = None,
        name_id: Optional[str] = None,
        request_id: Optional[str] = None,
        attributes: Optional[Mapping[str, Any]] = None,
        encrypted: bool = False,
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SamlSpError("SAML federation disabled")
        if encrypted and not self.cfg.allow_encrypted_assertions:
            raise SamlSpError("encrypted assertions not allowed")
        target = idp_entity_id
        if request_id:
            with self._lock:
                pending = self._pending.get(request_id)
            if pending:
                target = target or pending.get("idp")
        idp_entry = self.get_idp(str(target or "")) if target else None
        if idp_entry is None:
            idps = self.list_idps()
            if not idps:
                raise SamlSpError("no federated IdPs configured")
            idp_entry = self.get_idp(idps[0]["entity_id"])
        assert idp_entry is not None

        fake_idp = FakeSamlIdp(entity_id=idp_entry.entity_id)
        assertion = fake_idp.issue_assertion(
            name_id=name_id or "federated-user",
            audience=self.cfg.entity_id,
            attributes=attributes,
        )
        xml = (
            f"<Assertion ID='{assertion['id']}' Issuer='{idp_entry.entity_id}' "
            f"NameID='{assertion['name_id']}' Audience='{self.cfg.entity_id}'/>"
        ).encode("utf-8")
        if encrypted:
            # Soft encrypted stub — base64 wrap only
            xml = base64.b64encode(xml)
            enc_note = "soft-encrypted"
        else:
            enc_note = "plaintext"

        sig = self.crypto.sign(xml)
        if self.cfg.require_signed_assertions:
            if not self.crypto.verify(xml, sig):
                raise SamlSpError("assertion signature verification failed")

        session_id = secrets.token_urlsafe(16)
        session = {
            "session_id": session_id,
            "name_id": assertion["name_id"],
            "idp": idp_entry.entity_id,
            "attributes": dict(assertion["attributes"]),
            "assertion_id": assertion["id"],
            "signature": sig,
            "encryption": enc_note,
            "backend": "federation_fake",
            "production": False,
            "at": time.time(),
        }
        with self._lock:
            if request_id and request_id in self._pending:
                del self._pending[request_id]
            self._sessions[session_id] = dict(session)
        return {
            "ok": True,
            "session": session,
            "saml_response_b64": assertion["saml_response_b64"],
            "certification": False,
            "production": False,
        }

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            s = self._sessions.get(session_id)
            return dict(s) if s else None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            crypto_stats = (
                self.crypto.stats()
                if hasattr(self.crypto, "stats")
                else {"backend": "fake"}
            )
            return {
                "enabled": self.cfg.enabled,
                "entity_id": self.cfg.entity_id,
                "allow_live": self.cfg.allow_live,
                "require_signed_assertions": self.cfg.require_signed_assertions,
                "allow_encrypted_assertions": self.cfg.allow_encrypted_assertions,
                "idps": len([i for i in self.idps if i.enabled]),
                "pending": len(self._pending),
                "sessions": len(self._sessions),
                "pysaml2": pysaml2_available(),
                "xmlsec": xmlsec_available(),
                "crypto": crypto_stats,
            }


def build_saml_federation(
    cfg: Optional[Mapping[str, Any] | SamlFederationConfig] = None,
) -> Optional[SamlFederation]:
    raw: Mapping[str, Any] = cfg if isinstance(cfg, Mapping) else {}
    if isinstance(cfg, SamlFederationConfig):
        resolved = cfg
    else:
        resolved = SamlFederationConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None
    idps = _parse_idps(raw.get("idps") or [])
    if not idps:
        idps = [
            IdpFederationEntry(
                entity_id="https://idp.test/saml",
                sso_url="https://idp.test/saml/sso",
                display_name="Test IdP",
            ),
            IdpFederationEntry(
                entity_id="https://corp.example/idp",
                sso_url="https://corp.example/idp/sso",
                display_name="Corp IdP",
                metadata_url="https://corp.example/idp/metadata",
            ),
        ]
    if resolved.allow_live:
        crypto: FakeXmlSignature | SoftXmlsecVerifier = SoftXmlsecVerifier(
            allow_live=True
        )
    else:
        crypto = FakeXmlSignature()
    return SamlFederation(cfg=resolved, idps=idps, crypto=crypto)
