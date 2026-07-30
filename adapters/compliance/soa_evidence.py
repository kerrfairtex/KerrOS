"""
adapters/compliance/soa_evidence.py
===================================
Auditor evidence pack foundation (ADR-044).

Default-off. Assembles SoA draft + detached signature + residual-risk
catalog + control evidence index into a pack directory (and optional
zip). Soft openssl manifest signing when allow_live. Never claims ISO
certification — ``certification`` is always False.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from adapters.compliance.soa import SoaDraft, build_soa_draft
from adapters.compliance.soa_audit import (
    FakeSigner,
    SoaAuditConfig,
    SoaAuditor,
    SoftOpensslSigner,
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class SoaEvidenceError(RuntimeError):
    """Auditor evidence pack failed."""


DEFAULT_RESIDUAL_RISKS: list[dict[str, Any]] = [
    {
        "id": "RR-01",
        "control": "A.5.1",
        "theme": "Policies for information security",
        "residual": "medium",
        "treatment": "accept",
        "note": "Foundation residual — not an auditor finding",
    },
    {
        "id": "RR-02",
        "control": "A.8.24",
        "theme": "Use of cryptography",
        "residual": "low",
        "treatment": "mitigate",
        "note": "Soft crypto-shred / TLS foundations present",
    },
    {
        "id": "RR-03",
        "control": "A.5.17",
        "theme": "Authentication information",
        "residual": "medium",
        "treatment": "mitigate",
        "note": "OIDC/SAML foundations; production federation gated",
    },
]


@dataclass
class SoaEvidenceConfig:
    enabled: bool = False
    org_name: str = "KerrOS"
    output_dir: str = "data/soa/evidence"
    allow_write: bool = False
    allow_zip: bool = False
    allow_live: bool = False
    signer_backend: str = "fake"  # fake | openssl
    key_path: str = ""
    signer_id: str = "auditor@kerros.test"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "SoaEvidenceConfig":
        data = dict(raw or {})
        nested = (
            data.get("soa_evidence")
            if isinstance(data.get("soa_evidence"), dict)
            else data
        )
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_SOA_EVIDENCE")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        org = os.environ.get("KERROS_SOA_EVIDENCE_ORG")
        if org is None:
            org = str(nested.get("org_name") or "KerrOS")

        out_dir = os.environ.get("KERROS_SOA_EVIDENCE_DIR")
        if out_dir is None:
            out_dir = str(nested.get("output_dir") or "data/soa/evidence")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow_write = nested.get("allow_write", False)
        env_w = os.environ.get("KERROS_SOA_EVIDENCE_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_zip = nested.get("allow_zip", False)
        env_z = os.environ.get("KERROS_SOA_EVIDENCE_ZIP")
        if env_z is not None:
            allow_zip = _truthy(env_z)
        else:
            allow_zip = _truthy(allow_zip)

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_SOA_EVIDENCE_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        backend = os.environ.get("KERROS_SOA_EVIDENCE_SIGNER")
        if backend is None:
            backend = str(nested.get("signer_backend") or "fake")

        key_path = os.environ.get("KERROS_SOA_EVIDENCE_KEY")
        if key_path is None:
            key_path = str(nested.get("key_path") or "")

        signer = os.environ.get("KERROS_SOA_EVIDENCE_SIGNER_ID")
        if signer is None:
            signer = str(nested.get("signer_id") or "auditor@kerros.test")

        return cls(
            enabled=bool(enabled),
            org_name=str(org or "KerrOS").strip() or "KerrOS",
            output_dir=str(path),
            allow_write=bool(allow_write),
            allow_zip=bool(allow_zip),
            allow_live=bool(allow_live),
            signer_backend=str(backend or "fake").strip().lower() or "fake",
            key_path=str(key_path or "").strip(),
            signer_id=str(signer or "auditor@kerros.test").strip(),
        )


@dataclass
class SoaEvidencePack:
    """Build an auditor evidence pack from SoA draft + signature."""

    cfg: SoaEvidenceConfig
    soa: SoaDraft | None = None
    auditor: SoaAuditor | None = None
    residual_risks: list[dict[str, Any]] = field(
        default_factory=lambda: [dict(r) for r in DEFAULT_RESIDUAL_RISKS]
    )
    _packs: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _ensure_soa(self) -> SoaDraft:
        if self.soa is not None:
            return self.soa
        draft = build_soa_draft(
            {
                "enabled": True,
                "org_name": self.cfg.org_name,
                "allow_write": False,
            }
        )
        if draft is None:
            raise SoaEvidenceError("SoA draft unavailable")
        self.soa = draft
        return draft

    def _ensure_auditor(self) -> SoaAuditor:
        if self.auditor is not None:
            return self.auditor
        if self.cfg.signer_backend == "openssl":
            signer = SoftOpensslSigner(
                allow_live=self.cfg.allow_live,
                key_path=self.cfg.key_path,
                signer_id=self.cfg.signer_id,
            )
        else:
            signer = FakeSigner(signer_id=self.cfg.signer_id)
        self.auditor = SoaAuditor(
            cfg=SoaAuditConfig(
                enabled=True,
                backend=self.cfg.signer_backend,
                allow_live=self.cfg.allow_live,
                allow_write=False,
                signer_id=self.cfg.signer_id,
                key_path=self.cfg.key_path,
            ),
            signer=signer,
            soa=self._ensure_soa(),
        )
        return self.auditor

    def build_manifest(self) -> dict[str, Any]:
        soa = self._ensure_soa()
        draft = soa.build()
        auditor = self._ensure_auditor()
        signature = auditor.sign(draft)
        controls = list(draft.get("controls") or [])
        evidence_index = [
            {
                "control_id": str(c.get("id") or ""),
                "artifact": str(c.get("artifact") or ""),
                "status": str(c.get("status") or "planned"),
            }
            for c in controls
        ]
        with self._lock:
            residuals = [dict(r) for r in self.residual_risks]
        return {
            "document": "ISO/IEC 27001 auditor evidence pack (foundation)",
            "org_name": self.cfg.org_name,
            "standard": "ISO/IEC 27001:2022",
            "certification": False,
            "note": "Operator evidence aid — not a certified auditor pack",
            "generated_at": time.time(),
            "soa_draft": draft,
            "soa_signature": signature,
            "evidence_index": evidence_index,
            "residual_risks": residuals,
            "summary": {
                "controls": len(controls),
                "residuals": len(residuals),
                "signed": True,
            },
        }

    def _sign_manifest_bytes(self, payload: bytes) -> dict[str, Any]:
        auditor = self._ensure_auditor()
        return auditor.signer.sign(payload)

    def assemble(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SoaEvidenceError("SoA evidence pack disabled")
        manifest = self.build_manifest()
        canonical = json.dumps(
            manifest, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        pack_sig = self._sign_manifest_bytes(canonical)
        pack = {
            "manifest": manifest,
            "pack_signature": pack_sig,
            "pack_sha256": hashlib.sha256(canonical).hexdigest(),
            "certification": False,
            "at": time.time(),
        }
        if not self.cfg.allow_write:
            with self._lock:
                self._packs += 1
                self._last = {
                    "ok": True,
                    "skipped_write": True,
                    "pack_sha256": pack["pack_sha256"],
                }
            return {
                "ok": True,
                "skipped_write": True,
                "pack": pack,
                "note": "in-memory pack — set allow_write to persist",
            }

        out_dir = Path(self.cfg.output_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        soa_path = out_dir / "soa_draft.json"
        soa_path.write_text(
            json.dumps(manifest["soa_draft"], indent=2) + "\n", encoding="utf-8"
        )
        written.append(str(soa_path))

        sig_path = out_dir / "soa_draft.sig.json"
        sig_path.write_text(
            json.dumps(manifest["soa_signature"], indent=2) + "\n", encoding="utf-8"
        )
        written.append(str(sig_path))

        idx_path = out_dir / "evidence_index.json"
        idx_path.write_text(
            json.dumps(manifest["evidence_index"], indent=2) + "\n", encoding="utf-8"
        )
        written.append(str(idx_path))

        risk_path = out_dir / "residual_risks.json"
        risk_path.write_text(
            json.dumps(manifest["residual_risks"], indent=2) + "\n", encoding="utf-8"
        )
        written.append(str(risk_path))

        man_path = out_dir / "manifest.json"
        man_path.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
        written.append(str(man_path))

        zip_path = ""
        if self.cfg.allow_zip:
            zpath = out_dir.parent / "soa_evidence_pack.zip"
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name in (
                    "soa_draft.json",
                    "soa_draft.sig.json",
                    "evidence_index.json",
                    "residual_risks.json",
                    "manifest.json",
                ):
                    zf.write(out_dir / name, arcname=name)
            zip_path = str(zpath)
            written.append(zip_path)

        out = {
            "ok": True,
            "dir": str(out_dir),
            "written": written,
            "zip": zip_path,
            "pack_sha256": pack["pack_sha256"],
            "certification": False,
            "at": time.time(),
        }
        with self._lock:
            self._packs += 1
            self._last = {
                "ok": True,
                "dir": str(out_dir),
                "pack_sha256": pack["pack_sha256"],
                "zip": bool(zip_path),
            }
        return out

    def soft_openssl_pack_sign(self, payload: bytes) -> dict[str, Any]:
        """Soft openssl dgst over pack bytes when allow_live."""
        if not self.cfg.allow_live or not shutil.which("openssl") or not self.cfg.key_path:
            return {
                "ok": True,
                "dry_run": True,
                "openssl": bool(shutil.which("openssl")),
                "note": "skipped live pack sign",
            }
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", self.cfg.key_path, "-hex"],
            input=payload,
            capture_output=True,
            timeout=15,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stderr": proc.stderr.decode("utf-8", errors="replace")[:200],
        }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "org_name": self.cfg.org_name,
                "allow_write": self.cfg.allow_write,
                "allow_zip": self.cfg.allow_zip,
                "allow_live": self.cfg.allow_live,
                "signer_backend": self.cfg.signer_backend,
                "packs": self._packs,
                "residuals": len(self.residual_risks),
                "last": dict(self._last),
            }


def build_soa_evidence(
    cfg: Optional[Mapping[str, Any] | SoaEvidenceConfig] = None,
    *,
    soa: Optional[SoaDraft] = None,
    auditor: Optional[SoaAuditor] = None,
    base: Optional[Path] = None,
) -> Optional[SoaEvidencePack]:
    if isinstance(cfg, SoaEvidenceConfig):
        resolved = cfg
    else:
        resolved = SoaEvidenceConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return SoaEvidencePack(cfg=resolved, soa=soa, auditor=auditor)
