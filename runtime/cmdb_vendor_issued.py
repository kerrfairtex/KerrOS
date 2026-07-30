"""
runtime/cmdb_vendor_issued.py
=============================
Vendor-issued partnership certificate foundation (ADR-047).

Default-off. Holds Fake/soft envelopes representing certificates
*issued by* ServiceNow / Device42 partner programs (distinct from
ADR-043 operator-authored evidence). Never claims a real vendor seal.
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

from runtime.nats_supercluster import _truthy


class VendorIssuedError(RuntimeError):
    """Vendor-issued certificate operation failed."""


DEFAULT_PROGRAMS = (
    ("servicenow-tech-partner", "servicenow", "Technology Partner"),
    ("device42-integration", "device42", "Integration Partner"),
)


@dataclass
class VendorIssuedConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    allow_write: bool = False
    output_dir: str = "data/vendor_issued"
    url_template: str = ""
    token: str = ""
    org_name: str = "KerrOS"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "VendorIssuedConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        out_dir = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_DIR")
        if out_dir is None:
            out_dir = str(data.get("output_dir") or "data/vendor_issued")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        url = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_URL")
        if url is None:
            url = str(data.get("url_template") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        org = os.environ.get("KERROS_ACTOR_MESH_VENDOR_ISSUED_ORG")
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
class VendorIssuedRegistry:
    """Fake/soft vendor-issued partnership certificates."""

    cfg: VendorIssuedConfig
    _certs: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _key: bytes = b"kerros-vendor-issued-fake-key"

    def _fake_issue(self, program_id: str, vendor: str, program: str) -> dict[str, Any]:
        serial = f"VI-{uuid.uuid4().hex[:10].upper()}"
        tbs = f"{serial}|{program_id}|{self.cfg.org_name}".encode("utf-8")
        sig = hmac.new(self._key, tbs, hashlib.sha256).hexdigest()
        return {
            "serial": serial,
            "program_id": program_id,
            "vendor": vendor,
            "program": program,
            "subject": self.cfg.org_name,
            "issuer": f"{vendor} Partner Program (fake)",
            "signature": sig,
            "issued_at": time.time(),
            "expires_at": time.time() + 86400 * 365,
            "vendor_sealed": False,
            "backend": "fake",
            "note": "Fake vendor-issued cert — not a real partner seal",
        }

    def _http_fetch(self, program_id: str) -> dict[str, Any]:
        if not self.cfg.allow_live or not self.cfg.url_template:
            for pid, vendor, program in DEFAULT_PROGRAMS:
                if pid == program_id:
                    out = self._fake_issue(pid, vendor, program)
                    out["dry_run"] = True
                    return out
            raise VendorIssuedError(f"unknown program: {program_id}")
        url = self.cfg.url_template.format(program_id=program_id)
        headers = {"Accept": "application/json", "User-Agent": "kerros-vendor-issued/1.0"}
        if self.cfg.token:
            headers["Authorization"] = f"Bearer {self.cfg.token}"
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            return {
                "serial": str(data.get("serial") or f"VI-{uuid.uuid4().hex[:10].upper()}"),
                "program_id": program_id,
                "vendor": str(data.get("vendor") or ""),
                "program": str(data.get("program") or ""),
                "subject": str(data.get("subject") or self.cfg.org_name),
                "issuer": str(data.get("issuer") or "vendor-http"),
                "signature": str(data.get("signature") or ""),
                "issued_at": time.time(),
                "vendor_sealed": bool(data.get("vendor_sealed", False)),
                "backend": "http",
                "note": "Live fetch — still not auto-trusted as sealed without contract",
            }
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise VendorIssuedError(f"vendor cert fetch failed: {exc}") from exc

    def issue(self, program_id: str) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise VendorIssuedError("vendor-issued cert registry disabled")
        pid = str(program_id).strip()
        if self.cfg.backend == "http":
            cert = self._http_fetch(pid)
        else:
            match = next((p for p in DEFAULT_PROGRAMS if p[0] == pid), None)
            if match is None:
                raise VendorIssuedError(f"unknown program: {pid}")
            cert = self._fake_issue(*match)
        envelope = {
            "document": "Vendor-issued partnership certificate (foundation)",
            "certificate": cert,
            "vendor_sealed": False,
            "note": "Operator on-ramp — not a vendor-sealed production certificate",
            "at": time.time(),
        }
        if self.cfg.allow_write:
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{cert['serial']}.json"
            path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            envelope["path"] = str(path)
        with self._lock:
            self._certs.append(dict(envelope))
        return envelope

    def list_programs(self) -> list[dict[str, Any]]:
        return [
            {"id": pid, "vendor": vendor, "program": program}
            for pid, vendor, program in DEFAULT_PROGRAMS
        ]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "issued": len(self._certs),
                "programs": len(DEFAULT_PROGRAMS),
            }


def build_vendor_issued(
    cfg: Optional[Mapping[str, Any] | VendorIssuedConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[VendorIssuedRegistry]:
    if isinstance(cfg, VendorIssuedConfig):
        resolved = cfg
    else:
        resolved = VendorIssuedConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return VendorIssuedRegistry(cfg=resolved)
