"""
runtime/cmdb_vendor_cert.py
===========================
Certified vendor partnership facade (ADR-043).

Default-off. Tracks Soft partnership / certification evidence envelopes
for ServiceNow Technology Partner and Device42-style programs. Fake
registry for CI; soft HTTP status probe when allow_live. Does **not**
claim a real vendor certification.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.nats_supercluster import _truthy


class VendorCertError(RuntimeError):
    """Vendor certification facade failed."""


DEFAULT_PROGRAMS: list[dict[str, Any]] = [
    {
        "id": "servicenow-tech-partner",
        "vendor": "servicenow",
        "program": "Technology Partner",
        "tier": "foundation",
        "status": "planned",
        "certified": False,
    },
    {
        "id": "device42-integration",
        "vendor": "device42",
        "program": "Integration Partner",
        "tier": "foundation",
        "status": "planned",
        "certified": False,
    },
]


@runtime_checkable
class PartnershipProbe(Protocol):
    def probe(self, program_id: str) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakePartnershipProbe:
    """CI-safe partnership status stub."""

    _last: dict[str, Any] = field(default_factory=dict)

    def probe(self, program_id: str) -> dict[str, Any]:
        out = {
            "ok": True,
            "program_id": program_id,
            "status": "planned",
            "certified": False,
            "backend": "fake",
            "note": "Fake partnership probe — not a vendor certification",
            "at": time.time(),
        }
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake", "last": dict(self._last)}


@dataclass
class SoftHttpPartnershipProbe:
    """Soft HTTP JSON partnership status when allow_live."""

    url_template: str = ""
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 10.0
    _shadow: FakePartnershipProbe = field(default_factory=FakePartnershipProbe)
    _last: dict[str, Any] = field(default_factory=dict)

    def probe(self, program_id: str) -> dict[str, Any]:
        if not self.allow_live or not self.url_template.strip():
            out = self._shadow.probe(program_id)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        url = self.url_template.format(program_id=program_id)
        headers = {"Accept": "application/json", "User-Agent": "kerros-vendor-cert/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            out = {
                "ok": True,
                "program_id": program_id,
                "status": str(data.get("status") or "unknown"),
                "certified": bool(data.get("certified", False)),
                "backend": "http",
                "raw_keys": sorted(data.keys()) if isinstance(data, dict) else [],
                "at": time.time(),
                "note": "Live probe result — still not an automatic certification claim",
            }
            self._last = dict(out)
            return out
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise VendorCertError(f"partnership probe failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "http",
            "allow_live": self.allow_live,
            "url_template": self.url_template,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class VendorCertConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    allow_write: bool = False
    output_dir: str = "data/vendor_cert"
    url_template: str = ""
    token: str = ""
    org_name: str = "KerrOS"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "VendorCertConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        out_dir = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_DIR")
        if out_dir is None:
            out_dir = str(data.get("output_dir") or "data/vendor_cert")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        url = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_URL")
        if url is None:
            url = str(data.get("url_template") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        org = os.environ.get("KERROS_ACTOR_MESH_VENDOR_CERT_ORG")
        if org is None:
            org = str(data.get("org_name") or "KerrOS")

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_write=bool(allow_write),
            output_dir=str(path),
            url_template=str(url or "").strip(),
            token=str(token or "").strip(),
            org_name=str(org or "KerrOS").strip() or "KerrOS",
        )


@dataclass
class VendorCertRegistry:
    """Partnership program registry + evidence envelope builder."""

    cfg: VendorCertConfig
    probe: PartnershipProbe = field(default_factory=FakePartnershipProbe)
    programs: list[dict[str, Any]] = field(
        default_factory=lambda: [dict(p) for p in DEFAULT_PROGRAMS]
    )
    _evidence: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def list_programs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(p) for p in self.programs]

    def refresh(self, program_id: Optional[str] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise VendorCertError("vendor cert registry disabled")
        targets = [program_id] if program_id else [p["id"] for p in self.list_programs()]
        results: list[dict[str, Any]] = []
        for pid in targets:
            if not pid:
                continue
            result = self.probe.probe(str(pid))
            with self._lock:
                for p in self.programs:
                    if p["id"] == pid:
                        p["status"] = result.get("status", p.get("status"))
                        # Never flip certified=True from a soft probe alone
                        p["last_probe"] = result
            results.append(result)
        return {"ok": True, "probed": len(results), "results": results}

    def issue_evidence(self, program_id: str) -> dict[str, Any]:
        """Issue a *foundation* evidence envelope — certified always False."""
        if not self.cfg.enabled:
            raise VendorCertError("vendor cert registry disabled")
        programs = {p["id"]: p for p in self.list_programs()}
        prog = programs.get(str(program_id).strip())
        if prog is None:
            raise VendorCertError(f"unknown program: {program_id}")
        envelope = {
            "document": "Vendor partnership evidence (foundation)",
            "evidence_id": f"ev-{uuid.uuid4().hex[:12]}",
            "org_name": self.cfg.org_name,
            "program": dict(prog),
            "certified": False,
            "note": "Operator aid — not a vendor-issued certificate",
            "issued_at": time.time(),
        }
        if self.cfg.allow_write:
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{program_id}.evidence.json"
            path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            envelope["path"] = str(path)
        with self._lock:
            self._evidence.append(dict(envelope))
        return envelope

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "org_name": self.cfg.org_name,
                "programs": len(self.programs),
                "evidence": len(self._evidence),
                "probe": self.probe.stats(),
            }


def build_vendor_cert(
    cfg: Optional[Mapping[str, Any] | VendorCertConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[VendorCertRegistry]:
    if isinstance(cfg, VendorCertConfig):
        resolved = cfg
    else:
        resolved = VendorCertConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    if resolved.backend == "http":
        probe: PartnershipProbe = SoftHttpPartnershipProbe(
            url_template=resolved.url_template,
            token=resolved.token,
            allow_live=resolved.allow_live,
        )
    else:
        probe = FakePartnershipProbe()
    programs = None
    if isinstance(cfg, Mapping) and cfg.get("programs"):
        programs = [dict(p) for p in cfg.get("programs") or [] if isinstance(p, dict)]
    return VendorCertRegistry(
        cfg=resolved,
        probe=probe,
        programs=programs or [dict(p) for p in DEFAULT_PROGRAMS],
    )
