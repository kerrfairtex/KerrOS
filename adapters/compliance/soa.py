"""
adapters/compliance/soa.py
==========================
Certified Statement of Applicability (SoA) *foundation* (ADR-036).

Default-off. Builds a structured SoA draft mapping ISO 27001:2022 themes
to KerrOS artifacts with status planned|partial|implemented. This is an
operator draft aid — **not** a certification pack or auditor SoA.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class SoaError(RuntimeError):
    """SoA foundation failed."""


# Informative control rows — status reflects foundation code, not certification.
DEFAULT_CONTROLS: list[dict[str, Any]] = [
    {
        "id": "A.5.1",
        "theme": "Policies for information security",
        "status": "partial",
        "artifact": "docs/decisions/scope-lgu-vs-general.md",
    },
    {
        "id": "A.8.10",
        "theme": "Information deletion",
        "status": "partial",
        "artifact": "adapters/audit/erasure_ledger.py; adapters/audit/crypto_shred.py",
    },
    {
        "id": "A.8.11",
        "theme": "Data masking",
        "status": "partial",
        "artifact": "adapters/audit/privacy.py",
    },
    {
        "id": "A.8.12",
        "theme": "Data leakage prevention",
        "status": "partial",
        "artifact": "adapters/audit/residency.py; adapters/audit/transfer_ledger.py",
    },
    {
        "id": "A.8.15",
        "theme": "Logging",
        "status": "implemented",
        "artifact": "kernel/decision_log.py",
    },
    {
        "id": "A.8.16",
        "theme": "Monitoring activities",
        "status": "partial",
        "artifact": "adapters/audit/siem_forwarder.py",
    },
    {
        "id": "A.12.4",
        "theme": "Logging and monitoring",
        "status": "implemented",
        "artifact": "docs/compliance/iso27001-audit-logging-map.md",
    },
    {
        "id": "A.5.15",
        "theme": "Access control",
        "status": "partial",
        "artifact": "adapters/audit/rbac.py; adapters/auth/idp_portal.py",
    },
    {
        "id": "A.5.17",
        "theme": "Authentication information",
        "status": "partial",
        "artifact": "adapters/auth/oidc_rp.py",
    },
    {
        "id": "A.8.24",
        "theme": "Use of cryptography",
        "status": "partial",
        "artifact": "adapters/audit/crypto_shred.py; runtime/actor_mesh_tls.py",
    },
]


@dataclass
class SoaConfig:
    enabled: bool = False
    org_name: str = "KerrOS"
    output_dir: str = "data/soa"
    allow_write: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "SoaConfig":
        data = dict(raw or {})
        nested = data.get("compliance_soa") if isinstance(data.get("compliance_soa"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_COMPLIANCE_SOA")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        org = os.environ.get("KERROS_COMPLIANCE_SOA_ORG")
        if org is None:
            org = str(nested.get("org_name") or "KerrOS")

        out_dir = os.environ.get("KERROS_COMPLIANCE_SOA_DIR")
        if out_dir is None:
            out_dir = str(nested.get("output_dir") or "data/soa")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow_write = nested.get("allow_write", False)
        env_w = os.environ.get("KERROS_COMPLIANCE_SOA_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        return cls(
            enabled=bool(enabled),
            org_name=str(org or "KerrOS").strip() or "KerrOS",
            output_dir=str(path),
            allow_write=bool(allow_write),
        )


@dataclass
class SoaDraft:
    """In-memory SoA draft builder."""

    cfg: SoaConfig
    controls: list[dict[str, Any]] = field(default_factory=lambda: list(DEFAULT_CONTROLS))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def build(self) -> dict[str, Any]:
        with self._lock:
            controls = [dict(c) for c in self.controls]
        by_status: dict[str, int] = {}
        for c in controls:
            st = str(c.get("status") or "planned")
            by_status[st] = by_status.get(st, 0) + 1
        return {
            "document": "Statement of Applicability (draft foundation)",
            "org_name": self.cfg.org_name,
            "standard": "ISO/IEC 27001:2022",
            "certification": False,
            "note": "Operator draft aid — not a certified SoA pack",
            "generated_at": time.time(),
            "controls": controls,
            "summary": by_status,
        }

    def write_json(self) -> dict[str, Any]:
        draft = self.build()
        if not self.cfg.allow_write:
            return {"ok": False, "skipped": True, "error": "write disabled", "draft": draft}
        path = Path(self.cfg.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        out = path / "soa_draft.json"
        out.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(out), "controls": len(draft["controls"])}

    def stats(self) -> dict[str, Any]:
        draft = self.build()
        return {
            "enabled": self.cfg.enabled,
            "org_name": self.cfg.org_name,
            "allow_write": self.cfg.allow_write,
            "controls": len(draft["controls"]),
            "summary": draft["summary"],
            "certification": False,
        }


def build_soa_draft(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> SoaDraft | None:
    soa_cfg = SoaConfig.from_mapping(cfg, base=base)
    if not soa_cfg.enabled:
        return None
    return SoaDraft(cfg=soa_cfg)
