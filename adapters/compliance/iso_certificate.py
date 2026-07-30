"""
adapters/compliance/iso_certificate.py
======================================
Accredited ISO/IEC 27001 certificate-of-conformity foundation (ADR-047).

Default-off. Issues Fake accreditation envelopes and soft-probes an
external CAB URL when allow_live. ``iso_accredited`` stays False unless
a future contract sets ``allow_accredited`` *and* a live CAB confirms —
and even then KerrOS records foundation scope, never silent conformity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class IsoCertificateError(RuntimeError):
    """ISO certificate facade failed."""


@dataclass
class IsoCertificateConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    allow_write: bool = False
    allow_accredited: bool = False
    org_name: str = "KerrOS"
    standard: str = "ISO/IEC 27001:2022"
    cab_name: str = "Fake CAB"
    cab_url: str = ""
    token: str = ""
    output_dir: str = "data/soa/iso"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "IsoCertificateConfig":
        data = dict(raw or {})
        nested = (
            data.get("iso_certificate")
            if isinstance(data.get("iso_certificate"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_ISO_CERTIFICATE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ISO_CERTIFICATE_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_ISO_CERTIFICATE_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = nested.get("allow_write", False)
        env_w = os.environ.get("KERROS_ISO_CERTIFICATE_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_accredited = nested.get("allow_accredited", False)
        env_a = os.environ.get("KERROS_ISO_CERTIFICATE_ACCREDITED")
        if env_a is not None:
            allow_accredited = _truthy(env_a)
        else:
            allow_accredited = _truthy(allow_accredited)

        org = os.environ.get("KERROS_ISO_CERTIFICATE_ORG")
        if org is None:
            org = str(nested.get("org_name") or "KerrOS")

        standard = os.environ.get("KERROS_ISO_CERTIFICATE_STANDARD")
        if standard is None:
            standard = str(nested.get("standard") or "ISO/IEC 27001:2022")

        cab = os.environ.get("KERROS_ISO_CERTIFICATE_CAB")
        if cab is None:
            cab = str(nested.get("cab_name") or "Fake CAB")

        cab_url = os.environ.get("KERROS_ISO_CERTIFICATE_CAB_URL")
        if cab_url is None:
            cab_url = str(nested.get("cab_url") or "")

        token = os.environ.get("KERROS_ISO_CERTIFICATE_TOKEN")
        if token is None:
            token = str(nested.get("token") or "")

        out_dir = os.environ.get("KERROS_ISO_CERTIFICATE_DIR")
        if out_dir is None:
            out_dir = str(nested.get("output_dir") or "data/soa/iso")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_write=bool(allow_write),
            allow_accredited=bool(allow_accredited),
            org_name=str(org or "KerrOS").strip() or "KerrOS",
            standard=str(standard or "ISO/IEC 27001:2022").strip(),
            cab_name=str(cab or "Fake CAB").strip(),
            cab_url=str(cab_url or "").strip(),
            token=str(token or "").strip(),
            output_dir=str(path),
        )


@dataclass
class IsoCertificateService:
    """Fake/soft ISO certificate-of-conformity envelopes."""

    cfg: IsoCertificateConfig
    _issued: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _key: bytes = b"kerros-iso-cert-fake-key"

    def issue(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise IsoCertificateError("ISO certificate service disabled")
        serial = f"ISO-{uuid.uuid4().hex[:10].upper()}"
        cab_confirmed = False
        backend = "fake"
        if self.cfg.backend == "http" and self.cfg.allow_live and self.cfg.cab_url:
            headers = {
                "Accept": "application/json",
                "User-Agent": "kerros-iso-certificate/1.0",
            }
            if self.cfg.token:
                headers["Authorization"] = f"Bearer {self.cfg.token}"
            req = Request(self.cfg.cab_url, headers=headers, method="GET")
            try:
                with urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body.strip() else {}
                cab_confirmed = bool(data.get("accredited") or data.get("confirmed"))
                backend = "http"
                if data.get("serial"):
                    serial = str(data["serial"])
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                raise IsoCertificateError(f"CAB probe failed: {exc}") from exc

        tbs = f"{serial}|{self.cfg.org_name}|{self.cfg.standard}".encode("utf-8")
        sig = hmac.new(self._key, tbs, hashlib.sha256).hexdigest()
        # Never silently claim accreditation
        iso_accredited = bool(
            self.cfg.allow_accredited and cab_confirmed and backend == "http"
        )
        cert = {
            "serial": serial,
            "org_name": self.cfg.org_name,
            "standard": self.cfg.standard,
            "cab_name": self.cfg.cab_name,
            "signature": sig,
            "backend": backend,
            "cab_confirmed": cab_confirmed,
            "iso_accredited": iso_accredited,
            "issued_at": time.time(),
            "note": "Foundation ISO CoC envelope — not an accredited certificate",
        }
        envelope = {
            "document": "ISO/IEC 27001 certificate of conformity (foundation)",
            "certificate": cert,
            "certification": False,
            "iso_accredited": iso_accredited,
            "allow_accredited": self.cfg.allow_accredited,
            "note": (
                "Never a silent conformity claim — accredited only when "
                "allow_accredited + live CAB confirm"
            ),
            "at": time.time(),
        }
        if self.cfg.allow_write:
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{serial}.json"
            path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            envelope["path"] = str(path)
        with self._lock:
            self._issued.append(dict(envelope))
        return envelope

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "allow_accredited": self.cfg.allow_accredited,
                "issued": len(self._issued),
                "standard": self.cfg.standard,
            }


def build_iso_certificate(
    cfg: Optional[Mapping[str, Any] | IsoCertificateConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[IsoCertificateService]:
    if isinstance(cfg, IsoCertificateConfig):
        resolved = cfg
    else:
        resolved = IsoCertificateConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return IsoCertificateService(cfg=resolved)
