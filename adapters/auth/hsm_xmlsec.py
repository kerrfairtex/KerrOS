"""
adapters/auth/hsm_xmlsec.py
===========================
HSM-backed xmlsec XMLDSig foundation (ADR-047).

Default-off. Fake HSM token + soft xmlsec/PKCS#11 probes. Signs via
ADR-045 FakeXmlDsigEngine when HSM unavailable or not allow_live.
Never claims production HSM custody without explicit gates.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from adapters.auth.saml_federation import xmlsec_available
from adapters.auth.saml_sp import pysaml2_available
from adapters.auth.xmldsig import FakeXmlDsigEngine, XmlDsigError, c14n_fake


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def pkcs11_available() -> bool:
    try:
        import pkcs11  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class FakeHsmToken:
    """In-memory HSM token stub."""

    label: str = "kerros-fake-hsm"
    key_id: str = "sig-key-1"
    _ops: int = 0

    def sign(self, digest: bytes) -> bytes:
        self._ops += 1
        return hashlib.sha256(self.label.encode() + digest).digest()

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "fake_hsm",
            "label": self.label,
            "key_id": self.key_id,
            "ops": self._ops,
            "production": False,
        }


@dataclass
class SoftPkcs11Hsm:
    """Soft PKCS#11 probe — shadows Fake when not allow_live."""

    allow_live: bool = False
    module_path: str = ""
    pin: str = ""
    key_label: str = "kerros-sig"
    _shadow: FakeHsmToken = field(default_factory=FakeHsmToken)
    _last: dict[str, Any] = field(default_factory=dict)

    def sign(self, digest: bytes) -> bytes:
        if not self.allow_live or not pkcs11_available() or not self.module_path:
            out = self._shadow.sign(digest)
            self._last = {
                "ok": True,
                "dry_run": True,
                "pkcs11": pkcs11_available(),
                "module": self.module_path,
            }
            return out
        # Soft live: attempt import only; fall back to Fake on any failure
        try:
            import pkcs11

            lib = pkcs11.lib(self.module_path)
            # Minimal probe — real session wiring is contract-funded
            _ = lib
            sig = self._shadow.sign(digest)
            self._last = {
                "ok": True,
                "backend": "pkcs11_soft",
                "note": "module loaded — full session/sign deferred to contract",
            }
            return sig
        except Exception as exc:
            self._last = {"ok": False, "error": str(exc)[:200]}
            return self._shadow.sign(digest)

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "pkcs11",
            "allow_live": self.allow_live,
            "pkcs11": pkcs11_available(),
            "module_path": self.module_path,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class HsmXmlsecConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | pkcs11
    allow_live: bool = False
    allow_hsm: bool = False
    module_path: str = ""
    pin: str = ""
    key_label: str = "kerros-sig"
    allow_encryption: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "HsmXmlsecConfig":
        data = dict(raw or {})
        nested = (
            data.get("hsm_xmlsec") if isinstance(data.get("hsm_xmlsec"), dict) else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_HSM_XMLSEC")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_HSM_XMLSEC_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_HSM_XMLSEC_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_hsm = nested.get("allow_hsm", False)
        env_h = os.environ.get("KERROS_HSM_XMLSEC_HSM")
        if env_h is not None:
            allow_hsm = _truthy(env_h)
        else:
            allow_hsm = _truthy(allow_hsm)

        module = os.environ.get("KERROS_HSM_XMLSEC_MODULE")
        if module is None:
            module = str(nested.get("module_path") or "")

        pin = os.environ.get("KERROS_HSM_XMLSEC_PIN")
        if pin is None:
            pin = str(nested.get("pin") or "")

        key_label = os.environ.get("KERROS_HSM_XMLSEC_KEY")
        if key_label is None:
            key_label = str(nested.get("key_label") or "kerros-sig")

        allow_enc = nested.get("allow_encryption", False)
        env_e = os.environ.get("KERROS_HSM_XMLSEC_ENCRYPT")
        if env_e is not None:
            allow_enc = _truthy(env_e)
        else:
            allow_enc = _truthy(allow_enc)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_hsm=bool(allow_hsm),
            module_path=str(module or "").strip(),
            pin=str(pin or "").strip(),
            key_label=str(key_label or "kerros-sig").strip(),
            allow_encryption=bool(allow_enc),
        )


@dataclass
class HsmXmlsecService:
    """XMLDSig via Fake or soft HSM + xmlsec probes."""

    cfg: HsmXmlsecConfig
    hsm: FakeHsmToken | SoftPkcs11Hsm = field(default_factory=FakeHsmToken)
    engine: FakeXmlDsigEngine = field(default_factory=FakeXmlDsigEngine)
    _ops: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sign(self, xml: str | bytes, *, reference_uri: str = "") -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("HSM xmlsec service disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        # Base XMLDSig envelope from Fake engine
        sig = self.engine.sign(raw, reference_uri=reference_uri)
        # Optionally bind HSM digest signature
        if self.cfg.allow_hsm:
            canonical = c14n_fake(raw)
            digest = hashlib.sha256(canonical).digest()
            hsm_sig = self.hsm.sign(digest)
            sig["hsm_signature"] = hsm_sig.hex()
            sig["hsm"] = True
        else:
            sig["hsm"] = False
        sig["xmlsec"] = xmlsec_available()
        sig["pkcs11"] = pkcs11_available()
        sig["openssl"] = bool(shutil.which("openssl"))
        sig["production"] = False
        sig["backend"] = "hsm_xmlsec_foundation"
        with self._lock:
            self._ops += 1
            self._last = {
                "op": "sign",
                "hsm": sig["hsm"],
                "id": sig.get("id"),
            }
        return sig

    def verify(self, xml: str | bytes, signature: Mapping[str, Any]) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("HSM xmlsec service disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        ok = self.engine.verify(raw, signature)
        return {"ok": ok, "production": False, "hsm": bool(signature.get("hsm"))}

    def encrypt(self, xml: str | bytes) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise XmlDsigError("HSM xmlsec service disabled")
        if not self.cfg.allow_encryption:
            raise XmlDsigError("HSM XML encryption disabled")
        raw = xml.encode("utf-8") if isinstance(xml, str) else xml
        out = self.engine.encrypt(raw)
        out["hsm"] = self.cfg.allow_hsm
        out["production"] = False
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_hsm": self.cfg.allow_hsm,
                "allow_encryption": self.cfg.allow_encryption,
                "ops": self._ops,
                "last": dict(self._last),
                "hsm": self.hsm.stats(),
                "xmlsec": xmlsec_available(),
                "pysaml2": pysaml2_available(),
                "pkcs11": pkcs11_available(),
                "at": time.time(),
            }


def build_hsm_xmlsec(
    cfg: Optional[Mapping[str, Any] | HsmXmlsecConfig] = None,
) -> Optional[HsmXmlsecService]:
    if isinstance(cfg, HsmXmlsecConfig):
        resolved = cfg
    else:
        resolved = HsmXmlsecConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None
    if resolved.backend == "pkcs11":
        hsm: FakeHsmToken | SoftPkcs11Hsm = SoftPkcs11Hsm(
            allow_live=resolved.allow_live and resolved.allow_hsm,
            module_path=resolved.module_path,
            pin=resolved.pin,
            key_label=resolved.key_label,
        )
    else:
        hsm = FakeHsmToken(label=resolved.key_label)
    return HsmXmlsecService(cfg=resolved, hsm=hsm)
