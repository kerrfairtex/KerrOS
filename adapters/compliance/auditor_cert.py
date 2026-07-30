"""
adapters/compliance/auditor_cert.py
===================================
Auditor-issued certificate foundation (ADR-045).

Default-off. Issues Fake/soft X.509-style certificate envelopes over
ADR-044 evidence pack digests. Soft openssl when allow_live. Does **not**
claim ISO certification unless an explicit future contract sets
``allow_claim`` — and even then the envelope records foundation scope.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from adapters.compliance.soa_evidence import SoaEvidenceConfig, SoaEvidencePack, build_soa_evidence


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class AuditorCertError(RuntimeError):
    """Auditor certificate operation failed."""


@runtime_checkable
class AuditorCa(Protocol):
    def issue(self, *, subject: str, pack_sha256: str) -> dict[str, Any]: ...

    def verify(self, cert: Mapping[str, Any], *, pack_sha256: str) -> bool: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeAuditorCa:
    """HMAC-backed Fake auditor CA for CI."""

    ca_name: str = "KerrOS Fake Auditor CA"
    key: bytes = b"kerros-auditor-ca-fake-key"
    _issued: int = 0

    def issue(self, *, subject: str, pack_sha256: str) -> dict[str, Any]:
        serial = f"AC-{uuid.uuid4().hex[:12].upper()}"
        tbs = f"{serial}|{subject}|{pack_sha256}|{self.ca_name}".encode("utf-8")
        sig = hmac.new(self.key, tbs, hashlib.sha256).hexdigest()
        self._issued += 1
        return {
            "serial": serial,
            "subject": subject,
            "issuer": self.ca_name,
            "pack_sha256": pack_sha256,
            "not_before": time.time(),
            "not_after": time.time() + 86400 * 365,
            "signature": sig,
            "alg": "HMAC-SHA256-FAKE-X509",
            "pem_stub": (
                "-----BEGIN FAKE AUDITOR CERT-----\n"
                f"{sig[:64]}\n"
                "-----END FAKE AUDITOR CERT-----\n"
            ),
            "backend": "fake",
            "iso_certified": False,
            "note": "Fake auditor certificate — not an ISO-issued cert",
        }

    def verify(self, cert: Mapping[str, Any], *, pack_sha256: str) -> bool:
        if str(cert.get("pack_sha256") or "") != pack_sha256:
            return False
        serial = str(cert.get("serial") or "")
        subject = str(cert.get("subject") or "")
        issuer = str(cert.get("issuer") or self.ca_name)
        tbs = f"{serial}|{subject}|{pack_sha256}|{issuer}".encode("utf-8")
        expected = hmac.new(self.key, tbs, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, str(cert.get("signature") or ""))

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake", "ca_name": self.ca_name, "issued": self._issued}


@dataclass
class SoftOpensslAuditorCa:
    """Soft openssl req/x509 when allow_live; else Fake."""

    allow_live: bool = False
    ca_key_path: str = ""
    ca_name: str = "KerrOS Soft Auditor CA"
    _shadow: FakeAuditorCa = field(default_factory=FakeAuditorCa)
    _last: dict[str, Any] = field(default_factory=dict)

    def issue(self, *, subject: str, pack_sha256: str) -> dict[str, Any]:
        if not self.allow_live or not shutil.which("openssl"):
            out = self._shadow.issue(subject=subject, pack_sha256=pack_sha256)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        # Soft: generate a self-signed stub cert embedding pack hash in CN
        try:
            with tempfile.TemporaryDirectory() as td:
                key_path = Path(td) / "key.pem"
                csr_path = Path(td) / "req.pem"
                crt_path = Path(td) / "cert.pem"
                cn = f"pack-{pack_sha256[:16]}"
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-new",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-keyout",
                        str(key_path),
                        "-out",
                        str(csr_path),
                        "-subj",
                        f"/CN={cn}/O={subject}/OU=EvidencePack",
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                sign_cmd = [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    str(csr_path),
                    "-signkey",
                    str(key_path),
                    "-out",
                    str(crt_path),
                    "-days",
                    "365",
                ]
                if self.ca_key_path and Path(self.ca_key_path).is_file():
                    # Prefer provided CA key as signkey if present (still soft)
                    sign_cmd = [
                        "openssl",
                        "x509",
                        "-req",
                        "-in",
                        str(csr_path),
                        "-signkey",
                        self.ca_key_path,
                        "-out",
                        str(crt_path),
                        "-days",
                        "365",
                    ]
                proc = subprocess.run(
                    sign_cmd, capture_output=True, timeout=30, check=False
                )
                pem = (
                    crt_path.read_text(encoding="utf-8")
                    if crt_path.is_file()
                    else ""
                )
                out = {
                    "serial": f"AC-{uuid.uuid4().hex[:12].upper()}",
                    "subject": subject,
                    "issuer": self.ca_name,
                    "pack_sha256": pack_sha256,
                    "not_before": time.time(),
                    "not_after": time.time() + 86400 * 365,
                    "signature": hashlib.sha256(pem.encode("utf-8")).hexdigest()
                    if pem
                    else "",
                    "alg": "openssl-x509-soft",
                    "pem_stub": pem or self._shadow.issue(
                        subject=subject, pack_sha256=pack_sha256
                    )["pem_stub"],
                    "backend": "openssl",
                    "iso_certified": False,
                    "returncode": proc.returncode,
                    "note": "Soft openssl cert — not an ISO auditor-issued certificate",
                }
                self._last = dict(out)
                return out
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AuditorCertError(f"openssl auditor CA failed: {exc}") from exc

    def verify(self, cert: Mapping[str, Any], *, pack_sha256: str) -> bool:
        if str(cert.get("backend") or "") == "fake" or cert.get("dry_run"):
            return self._shadow.verify(cert, pack_sha256=pack_sha256)
        return str(cert.get("pack_sha256") or "") == pack_sha256

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "openssl",
            "allow_live": self.allow_live,
            "openssl": bool(shutil.which("openssl")),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class AuditorCertConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | openssl
    allow_live: bool = False
    allow_write: bool = False
    allow_claim: bool = False  # still foundation unless contract-funded
    ca_name: str = "KerrOS Auditor CA"
    ca_key_path: str = ""
    subject: str = "KerrOS Evidence Pack"
    output_dir: str = "data/soa/certs"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "AuditorCertConfig":
        data = dict(raw or {})
        nested = (
            data.get("auditor_cert")
            if isinstance(data.get("auditor_cert"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_AUDITOR_CERT")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_AUDITOR_CERT_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_AUDITOR_CERT_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = nested.get("allow_write", False)
        env_w = os.environ.get("KERROS_AUDITOR_CERT_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_claim = nested.get("allow_claim", False)
        env_c = os.environ.get("KERROS_AUDITOR_CERT_CLAIM")
        if env_c is not None:
            allow_claim = _truthy(env_c)
        else:
            allow_claim = _truthy(allow_claim)

        ca_name = os.environ.get("KERROS_AUDITOR_CERT_CA")
        if ca_name is None:
            ca_name = str(nested.get("ca_name") or "KerrOS Auditor CA")

        ca_key = os.environ.get("KERROS_AUDITOR_CERT_CA_KEY")
        if ca_key is None:
            ca_key = str(nested.get("ca_key_path") or "")

        subject = os.environ.get("KERROS_AUDITOR_CERT_SUBJECT")
        if subject is None:
            subject = str(nested.get("subject") or "KerrOS Evidence Pack")

        out_dir = os.environ.get("KERROS_AUDITOR_CERT_DIR")
        if out_dir is None:
            out_dir = str(nested.get("output_dir") or "data/soa/certs")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_write=bool(allow_write),
            allow_claim=bool(allow_claim),
            ca_name=str(ca_name or "KerrOS Auditor CA").strip(),
            ca_key_path=str(ca_key or "").strip(),
            subject=str(subject or "KerrOS Evidence Pack").strip(),
            output_dir=str(path),
        )


@dataclass
class AuditorCertificateService:
    """Issue / verify auditor certificates over evidence pack digests."""

    cfg: AuditorCertConfig
    ca: AuditorCa = field(default_factory=FakeAuditorCa)
    evidence: SoaEvidencePack | None = None
    _issued: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _pack_sha(self, pack_sha256: Optional[str] = None) -> str:
        if pack_sha256:
            return str(pack_sha256).strip()
        if self.evidence is None:
            raise AuditorCertError("no evidence pack or pack_sha256 provided")
        assembled = self.evidence.assemble()
        if assembled.get("pack_sha256"):
            return str(assembled["pack_sha256"])
        pack = assembled.get("pack") or {}
        sha = str(pack.get("pack_sha256") or "")
        if not sha:
            raise AuditorCertError("evidence pack missing pack_sha256")
        return sha

    def issue(self, *, pack_sha256: Optional[str] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AuditorCertError("auditor certificate service disabled")
        sha = self._pack_sha(pack_sha256)
        cert = self.ca.issue(subject=self.cfg.subject, pack_sha256=sha)
        # Even with allow_claim, never silently claim ISO — record foundation
        envelope = {
            "document": "Auditor-issued evidence certificate (foundation)",
            "certificate": cert,
            "iso_certified": bool(self.cfg.allow_claim and cert.get("iso_certified")),
            "certification": False,  # KerrOS never auto-claims ISO certification
            "allow_claim": self.cfg.allow_claim,
            "note": (
                "Foundation auditor cert envelope — not an ISO/IEC 27001 "
                "certificate of conformity"
            ),
            "issued_at": time.time(),
        }
        if self.cfg.allow_write:
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{cert['serial']}.json"
            path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            pem_path = out_dir / f"{cert['serial']}.pem"
            pem_path.write_text(str(cert.get("pem_stub") or ""), encoding="utf-8")
            envelope["path"] = str(path)
            envelope["pem_path"] = str(pem_path)
        with self._lock:
            self._issued.append(dict(envelope))
        return envelope

    def verify(
        self,
        cert_envelope: Mapping[str, Any],
        *,
        pack_sha256: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise AuditorCertError("auditor certificate service disabled")
        inner = dict(cert_envelope.get("certificate") or cert_envelope)
        sha = pack_sha256 or str(inner.get("pack_sha256") or "")
        if not sha:
            sha = self._pack_sha(None)
        ok = self.ca.verify(inner, pack_sha256=sha)
        return {
            "ok": ok,
            "pack_sha256": sha,
            "serial": inner.get("serial"),
            "iso_certified": False,
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "allow_claim": self.cfg.allow_claim,
                "issued": len(self._issued),
                "ca": self.ca.stats(),
            }


def build_auditor_cert(
    cfg: Optional[Mapping[str, Any] | AuditorCertConfig] = None,
    *,
    evidence: Optional[SoaEvidencePack] = None,
    evidence_cfg: Optional[Mapping[str, Any]] = None,
    base: Optional[Path] = None,
) -> Optional[AuditorCertificateService]:
    if isinstance(cfg, AuditorCertConfig):
        resolved = cfg
    else:
        resolved = AuditorCertConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    if resolved.backend == "openssl":
        ca: AuditorCa = SoftOpensslAuditorCa(
            allow_live=resolved.allow_live,
            ca_key_path=resolved.ca_key_path,
            ca_name=resolved.ca_name,
        )
    else:
        ca = FakeAuditorCa(ca_name=resolved.ca_name)
    pack = evidence
    if pack is None and evidence_cfg is not None:
        pack = build_soa_evidence(evidence_cfg, base=base)
    elif pack is None:
        # Soft-enable an in-memory evidence pack for cert binding
        pack = build_soa_evidence(
            SoaEvidenceConfig(enabled=True, allow_write=False, org_name="KerrOS"),
            base=base,
        )
    return AuditorCertificateService(cfg=resolved, ca=ca, evidence=pack)
