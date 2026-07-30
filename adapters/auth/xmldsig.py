"""
adapters/auth/xmldsig.py
========================
Full XMLDSig / XML encryption foundation (ADR-045).

Default-off. Builds XMLDSig-shaped SignedInfo envelopes with Fake HMAC
crypto for CI, and soft xmlsec/openssl probes when allow_live. Soft
EncryptedData stubs for assertion encryption. Not production XMLDSig.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from adapters.auth.saml_federation import FakeXmlSignature, xmlsec_available
from adapters.auth.saml_sp import pysaml2_available


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class XmlDsigError(RuntimeError):
    """XMLDSig operation failed."""


def c14n_fake(xml_bytes: bytes) -> bytes:
    """Minimal Fake canonicalization — collapse whitespace runs."""
    text = xml_bytes.decode("utf-8", errors="replace")
    collapsed = " ".join(text.split())
    return collapsed.encode("utf-8")


@dataclass
class FakeXmlDsigEngine:
    """XMLDSig-shaped envelopes signed with HMAC (CI-safe)."""

    key: bytes = b"kerros-xmldsig-fake-key"
    _signs: int = 0

    def sign(self, xml_bytes: bytes, *, reference_uri: str = "") -> dict[str, Any]:
        canonical = c14n_fake(xml_bytes)
        digest = hashlib.sha256(canonical).hexdigest()
        signed_info = (
            f"<SignedInfo>"
            f"<CanonicalizationMethod Algorithm='fake-c14n'/>"
            f"<SignatureMethod Algorithm='hmac-sha256-fake'/>"
            f"<Reference URI='{reference_uri}'>"
            f"<DigestMethod Algorithm='sha256'/>"
            f"<DigestValue>{digest}</DigestValue>"
            f"</Reference>"
            f"</SignedInfo>"
        ).encode("utf-8")
        sig_value = hmac.new(self.key, signed_info, hashlib.sha256).hexdigest()
        self._signs += 1
        return {
            "id": f"_sig{uuid.uuid4().hex[:12]}",
            "SignedInfo": signed_info.decode("utf-8"),
            "SignatureValue": sig_value,
            "DigestValue": digest,
            "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
            "alg": "XMLDSig-HMAC-SHA256-FAKE",
            "backend": "fake",
            "production": False,
            "signed_at": time.time(),
        }

    def verify(self, xml_bytes: bytes, signature: Mapping[str, Any]) -> bool:
        canonical = c14n_fake(xml_bytes)
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != str(signature.get("DigestValue") or ""):
            return False
        signed_info = str(signature.get("SignedInfo") or "").encode("utf-8")
        expected = hmac.new(self.key, signed_info, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(signature.get("SignatureValue") or ""))

    def encrypt(self, xml_bytes: bytes) -> dict[str, Any]:
        token = base64.b64encode(xml_bytes).decode("ascii")
        return {
            "EncryptedData": (
                f"<EncryptedData Type='Assertion'>"
                f"<CipherData><CipherValue>{token}</CipherValue></CipherData>"
                f"</EncryptedData>"
            ),
            "backend": "fake",
            "production": False,
        }

    def decrypt(self, envelope: Mapping[str, Any]) -> bytes:
        enc = str(envelope.get("EncryptedData") or "")
        start = enc.find("<CipherValue>")
        end = enc.find("</CipherValue>")
        if start < 0 or end < 0:
            raise XmlDsigError("CipherValue missing")
        token = enc[start + len("<CipherValue>") : end]
        return base64.b64decode(token.encode("ascii"))

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake", "signs": self._signs}


@dataclass
class SoftXmlsecEngine:
    """Soft xmlsec/openssl XMLDSig — shadows Fake when not allow_live."""

    allow_live: bool = False
    key_path: str = ""
    _shadow: FakeXmlDsigEngine = field(default_factory=FakeXmlDsigEngine)
    _last: dict[str, Any] = field(default_factory=dict)

    def sign(self, xml_bytes: bytes, *, reference_uri: str = "") -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.sign(xml_bytes, reference_uri=reference_uri)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        # Soft live: prefer Fake envelope annotated with tool availability
        out = self._shadow.sign(xml_bytes, reference_uri=reference_uri)
        out["backend"] = "soft_xmlsec"
        out["xmlsec"] = xmlsec_available()
        out["pysaml2"] = pysaml2_available()
        out["openssl"] = bool(shutil.which("openssl"))
        out["production"] = False
        out["note"] = "soft live XMLDSig — full xmlsec template wiring when funded"
        if self.key_path and shutil.which("openssl"):
            try:
                proc = subprocess.run(
                    ["openssl", "dgst", "-sha256", "-sign", self.key_path, "-hex"],
                    input=xml_bytes,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if proc.returncode == 0:
                    out["openssl_sig"] = (
                        proc.stdout.decode("utf-8", errors="replace").strip().split()[-1]
                    )
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._last = dict(out)
        return out

    def verify(self, xml_bytes: bytes, signature: Mapping[str, Any]) -> bool:
        return self._shadow.verify(xml_bytes, signature)

    def encrypt(self, xml_bytes: bytes) -> dict[str, Any]:
        out = self._shadow.encrypt(xml_bytes)
        if self.allow_live:
            out["backend"] = "soft_xmlsec"
            out["note"] = "soft EncryptedData stub"
        else:
            out["dry_run"] = True
        return out

    def decrypt(self, envelope: Mapping[str, Any]) -> bytes:
        return self._shadow.decrypt(envelope)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "soft_xmlsec",
            "allow_live": self.allow_live,
            "xmlsec": xmlsec_available(),
            "pysaml2": pysaml2_available(),
            "openssl": bool(shutil.which("openssl")),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class XmlDsigConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | xmlsec
    allow_live: bool = False
    key_path: str = ""
    allow_encryption: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "XmlDsigConfig":
        data = dict(raw or {})
        nested = (
            data.get("saml_xmldsig")
            if isinstance(data.get("saml_xmldsig"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_SAML_XMLDSIG")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_SAML_XMLDSIG_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_SAML_XMLDSIG_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        key_path = os.environ.get("KERROS_SAML_XMLDSIG_KEY")
        if key_path is None:
            key_path = str(nested.get("key_path") or "")

        allow_enc = nested.get("allow_encryption", False)
        env_e = os.environ.get("KERROS_SAML_XMLDSIG_ENCRYPT")
        if env_e is not None:
            allow_enc = _truthy(env_e)
        else:
            allow_enc = _truthy(allow_enc)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            key_path=str(key_path or "").strip(),
            allow_encryption=bool(allow_enc),
        )


@dataclass
class XmlDsigService:
    """Sign / verify / encrypt XML with Fake or soft XMLDSig engines."""

    cfg: XmlDsigConfig
    engine: FakeXmlDsigEngine | SoftXmlsecEngine = field(
        default_factory=FakeXmlDsigEngine
    )
    _ops: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sign(self, xml: str | bytes, *, reference_uri: str = "") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("XMLDSig service disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        out = self.engine.sign(raw, reference_uri=reference_uri)
        with self._lock:
            self._ops += 1
            self._last = {"op": "sign", "id": out.get("id"), "backend": out.get("backend")}
        return out

    def verify(self, xml: str | bytes, signature: Mapping[str, Any]) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("XMLDSig service disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        ok = self.engine.verify(raw, signature)
        return {"ok": ok, "production": False}

    def encrypt(self, xml: str | bytes) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("XMLDSig service disabled")
        if not self.cfg.allow_encryption:
            raise XmlDsigError("XML encryption disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        out = self.engine.encrypt(raw)
        with self._lock:
            self._ops += 1
            self._last = {"op": "encrypt", "backend": out.get("backend")}
        return out

    def decrypt(self, envelope: Mapping[str, Any]) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("XMLDSig service disabled")
        if not self.cfg.allow_encryption:
            raise XmlDsigError("XML encryption disabled")
        raw = self.engine.decrypt(envelope)
        return {"ok": True, "xml": raw.decode("utf-8", errors="replace"), "production": False}

    def sign_assertion(self, assertion_xml: str) -> dict[str, Any]:
        """Convenience: sign a SAML Assertion XML fragment."""
        sig = self.sign(assertion_xml, reference_uri="#assertion")
        wrapped = (
            f"<Assertion ID='assertion'>{assertion_xml}"
            f"<Signature>{sig['SignedInfo']}"
            f"<SignatureValue>{sig['SignatureValue']}</SignatureValue>"
            f"</Signature></Assertion>"
        )
        return {
            "ok": True,
            "signed_xml": wrapped,
            "signature": sig,
            "production": False,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_encryption": self.cfg.allow_encryption,
                "ops": self._ops,
                "last": dict(self._last),
                "engine": self.engine.stats(),
                "xmlsec": xmlsec_available(),
                "pysaml2": pysaml2_available(),
            }


def build_xmldsig(
    cfg: Optional[Mapping[str, Any] | XmlDsigConfig] = None,
) -> Optional[XmlDsigService]:
    if isinstance(cfg, XmlDsigConfig):
        resolved = cfg
    else:
        resolved = XmlDsigConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None
    if resolved.backend in ("xmlsec", "openssl", "soft"):
        engine: FakeXmlDsigEngine | SoftXmlsecEngine = SoftXmlsecEngine(
            allow_live=resolved.allow_live, key_path=resolved.key_path
        )
    else:
        engine = FakeXmlDsigEngine()
    return XmlDsigService(cfg=resolved, engine=engine)


# Re-export FakeXmlSignature for callers that still use federation stubs
__all__ = [
    "XmlDsigError",
    "XmlDsigConfig",
    "XmlDsigService",
    "FakeXmlDsigEngine",
    "SoftXmlsecEngine",
    "build_xmldsig",
    "c14n_fake",
    "FakeXmlSignature",
]
