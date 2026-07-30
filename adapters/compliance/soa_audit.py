"""
adapters/compliance/soa_audit.py
================================
Auditor-signed Statement of Applicability foundation (ADR-041).

Default-off. Detached signature over ADR-036 soa_draft.json using
FakeSigner (HMAC) or soft openssl when allow_live. Not a real
certification claim or auditor evidence pack.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from adapters.compliance.soa import SoaConfig, SoaDraft, build_soa_draft


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class SoaAuditError(RuntimeError):
    """Auditor SoA signing failed."""


@runtime_checkable
class SoaSigner(Protocol):
    def sign(self, payload: bytes) -> dict[str, Any]: ...

    def verify(self, payload: bytes, signature: Mapping[str, Any]) -> bool: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeSigner:
    """HMAC-SHA256 detached signature for CI."""

    key: bytes = b"kerros-soa-audit-fake-key"
    signer_id: str = "fake-auditor@kerros.test"
    _signs: int = 0

    def sign(self, payload: bytes) -> dict[str, Any]:
        digest = hmac.new(self.key, payload, hashlib.sha256).hexdigest()
        self._signs += 1
        return {
            "alg": "HMAC-SHA256",
            "signer": self.signer_id,
            "signature": digest,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "signed_at": time.time(),
            "backend": "fake",
            "certification": False,
        }

    def verify(self, payload: bytes, signature: Mapping[str, Any]) -> bool:
        expected = hmac.new(self.key, payload, hashlib.sha256).hexdigest()
        got = str(signature.get("signature") or "")
        return hmac.compare_digest(expected, got)

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake", "signer": self.signer_id, "signs": self._signs}


@dataclass
class SoftOpensslSigner:
    """Soft openssl dgst when allow_live and openssl present; else Fake."""

    allow_live: bool = False
    key_path: str = ""
    signer_id: str = "openssl-auditor@kerros.test"
    _shadow: FakeSigner = field(default_factory=FakeSigner)
    _last: dict[str, Any] = field(default_factory=dict)

    def sign(self, payload: bytes) -> dict[str, Any]:
        if not self.allow_live or not shutil.which("openssl") or not self.key_path:
            out = self._shadow.sign(payload)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        try:
            proc = subprocess.run(
                [
                    "openssl",
                    "dgst",
                    "-sha256",
                    "-sign",
                    self.key_path,
                    "-hex",
                ],
                input=payload,
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode != 0:
                raise SoaAuditError(proc.stderr.decode("utf-8", errors="replace")[:200])
            sig_hex = proc.stdout.decode("utf-8", errors="replace").strip().split()[-1]
            out = {
                "alg": "openssl-sha256",
                "signer": self.signer_id,
                "signature": sig_hex,
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "signed_at": time.time(),
                "backend": "openssl",
                "certification": False,
            }
            self._last = dict(out)
            return out
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SoaAuditError(f"openssl sign failed: {exc}") from exc

    def verify(self, payload: bytes, signature: Mapping[str, Any]) -> bool:
        if str(signature.get("backend") or "") == "fake" or signature.get("dry_run"):
            return self._shadow.verify(payload, signature)
        # Soft: re-check payload hash only when openssl verify not wired
        return str(signature.get("payload_sha256") or "") == hashlib.sha256(
            payload
        ).hexdigest()

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "openssl",
            "allow_live": self.allow_live,
            "openssl": bool(shutil.which("openssl")),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class SoaAuditConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | openssl
    allow_live: bool = False
    allow_write: bool = False
    key_path: str = ""
    signer_id: str = "auditor@kerros.test"
    output_dir: str = "data/soa"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "SoaAuditConfig":
        data = dict(raw or {})
        nested = data.get("soa_audit") if isinstance(data.get("soa_audit"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_SOA_AUDIT")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_SOA_AUDIT_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_SOA_AUDIT_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        allow_write = nested.get("allow_write", False)
        env_w = os.environ.get("KERROS_SOA_AUDIT_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        key_path = os.environ.get("KERROS_SOA_AUDIT_KEY")
        if key_path is None:
            key_path = str(nested.get("key_path") or "")

        signer = os.environ.get("KERROS_SOA_AUDIT_SIGNER")
        if signer is None:
            signer = str(nested.get("signer_id") or "auditor@kerros.test")

        out_dir = os.environ.get("KERROS_SOA_AUDIT_DIR")
        if out_dir is None:
            out_dir = str(nested.get("output_dir") or "data/soa")
        path = Path(out_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            allow_write=bool(allow_write),
            key_path=str(key_path or "").strip(),
            signer_id=str(signer or "auditor@kerros.test").strip(),
            output_dir=str(path),
        )


@dataclass
class SoaAuditor:
    """Sign / verify SoA draft JSON with detached auditor signature."""

    cfg: SoaAuditConfig
    signer: SoaSigner = field(default_factory=FakeSigner)
    soa: SoaDraft | None = None
    _signs: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _last_envelope: dict[str, Any] = field(default_factory=dict)
    _last_draft: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _draft_doc(self, draft: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if draft is not None:
            return dict(draft)
        if self.soa is not None:
            return self.soa.build()
        raise SoaAuditError("no SoA draft available")

    def _payload_bytes(self, doc: Mapping[str, Any]) -> bytes:
        return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def sign(self, draft: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SoaAuditError("SoA audit signing disabled")
        doc = self._draft_doc(draft)
        payload = self._payload_bytes(doc)
        sig = self.signer.sign(payload)
        envelope = {
            "document": "SoA auditor signature (foundation)",
            "certification": False,
            "note": "Detached signature aid — not a certified evidence pack",
            "signature": sig,
            "at": time.time(),
        }
        if self.cfg.allow_write:
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / "soa_draft.sig.json"
            path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
            envelope["path"] = str(path)
        with self._lock:
            self._signs += 1
            self._last_draft = dict(doc)
            self._last_envelope = dict(envelope)
            self._last = {
                "ok": True,
                "alg": sig.get("alg"),
                "signer": sig.get("signer"),
                "payload_sha256": sig.get("payload_sha256"),
            }
        return envelope

    def verify(
        self,
        draft: Optional[Mapping[str, Any]] = None,
        signature: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise SoaAuditError("SoA audit signing disabled")
        if draft is not None:
            doc = dict(draft)
        else:
            with self._lock:
                doc = dict(self._last_draft) if self._last_draft else {}
            if not doc:
                doc = self._draft_doc(None)
        payload = self._payload_bytes(doc)
        sig_doc = dict(signature or {})
        if not sig_doc:
            with self._lock:
                sig_doc = dict(self._last_envelope)
        if not sig_doc and self.cfg.allow_write:
            path = Path(self.cfg.output_dir) / "soa_draft.sig.json"
            if path.is_file():
                sig_doc = json.loads(path.read_text(encoding="utf-8"))
        inner = dict(sig_doc.get("signature") or sig_doc)
        ok = self.signer.verify(payload, inner)
        return {"ok": ok, "payload_sha256": hashlib.sha256(payload).hexdigest()}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "allow_write": self.cfg.allow_write,
                "signs": self._signs,
                "last": dict(self._last),
                "signer": self.signer.stats(),
            }


def build_soa_auditor(
    cfg: Optional[Mapping[str, Any] | SoaAuditConfig] = None,
    *,
    soa: Optional[SoaDraft] = None,
    soa_cfg: Optional[Mapping[str, Any] | SoaConfig] = None,
    base: Optional[Path] = None,
) -> Optional[SoaAuditor]:
    if isinstance(cfg, SoaAuditConfig):
        resolved = cfg
    else:
        resolved = SoaAuditConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    draft = soa
    if draft is None:
        if isinstance(soa_cfg, SoaConfig):
            draft = SoaDraft(cfg=soa_cfg) if soa_cfg.enabled else None
        else:
            draft = build_soa_draft(soa_cfg or {"enabled": True, "allow_write": False}, base=base)
    if resolved.backend == "openssl":
        signer: SoaSigner = SoftOpensslSigner(
            allow_live=resolved.allow_live,
            key_path=resolved.key_path,
            signer_id=resolved.signer_id,
        )
    else:
        signer = FakeSigner(signer_id=resolved.signer_id)
    return SoaAuditor(cfg=resolved, signer=signer, soa=draft)
