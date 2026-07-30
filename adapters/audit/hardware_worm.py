"""
adapters/audit/hardware_worm.py
===============================
Hardware WORM *appliance* facade (ADR-034).

Default-off. Soft HTTP/S3-compatible appliance client with an in-memory
fake for CI. Post-seal hook can mirror sealed segment bytes to the
appliance. Does **not** replace software-WORM; never mutates local sealed
segments.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import URLError
from urllib.request import Request, urlopen


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class HardwareWormError(RuntimeError):
    """Hardware WORM appliance operation failed."""


@runtime_checkable
class HardwareWormAppliance(Protocol):
    def put_object(self, key: str, body: bytes, *, meta: Optional[Mapping[str, Any]] = None) -> dict[str, Any]: ...

    def head_object(self, key: str) -> dict[str, Any] | None: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeHardwareWormAppliance:
    """CI-safe appliance that retains objects immutably in memory."""

    _objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def put_object(
        self, key: str, body: bytes, *, meta: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        k = str(key or "").strip()
        if not k:
            raise HardwareWormError("key required")
        with self._lock:
            if k in self._objects:
                raise HardwareWormError(f"WORM refuse overwrite: {k}")
            digest = hashlib.sha256(body).hexdigest()
            rec = {
                "key": k,
                "sha256": digest,
                "size": len(body),
                "meta": dict(meta or {}),
                "stored_at": time.time(),
            }
            self._objects[k] = {**rec, "body": body}
        return {"ok": True, "key": k, "sha256": digest, "size": len(body)}

    def head_object(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            rec = self._objects.get(str(key or "").strip())
            if not rec:
                return None
            return {k: v for k, v in rec.items() if k != "body"}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"provider": "fake", "objects": len(self._objects)}


@dataclass
class SoftHttpHardwareWormAppliance:
    """Soft PUT to an appliance HTTP endpoint when allow_live."""

    endpoint_url: str = ""
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 5.0
    _shadow: FakeHardwareWormAppliance = field(default_factory=FakeHardwareWormAppliance)
    _last: dict[str, Any] = field(default_factory=dict)

    def put_object(
        self, key: str, body: bytes, *, meta: Optional[Mapping[str, Any]] = None
    ) -> dict[str, Any]:
        if not self.allow_live:
            out = self._shadow.put_object(key, body, meta=meta)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        url = str(self.endpoint_url or "").rstrip("/")
        if not url:
            raise HardwareWormError("endpoint_url required")
        target = f"{url}/{key.lstrip('/')}"
        headers = {"Content-Type": "application/octet-stream", "User-Agent": "kerros-hworm/1"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            req = Request(target, data=body, method="PUT", headers=headers)
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                out = {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "key": key,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "size": len(body),
                }
            self._shadow.put_object(key, body, meta=meta)
            self._last = dict(out)
            return out
        except (URLError, OSError, HardwareWormError) as exc:
            self._last = {"ok": False, "error": str(exc)}
            raise HardwareWormError(str(exc)) from exc

    def head_object(self, key: str) -> dict[str, Any] | None:
        return self._shadow.head_object(key)

    def stats(self) -> dict[str, Any]:
        return {
            "provider": "http",
            "endpoint_url": self.endpoint_url,
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class HardwareWormConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    endpoint_url: str = ""
    token: str = ""
    prefix: str = "kerros/audit_worm/"
    strict: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "HardwareWormConfig":
        data = dict(raw or {})
        # Accept nested under audit_hardware_worm or direct.
        nested = data.get("audit_hardware_worm") if isinstance(data.get("audit_hardware_worm"), dict) else data
        nested = dict(nested or {})

        enabled = nested.get("enabled", False)
        env = os.environ.get("KERROS_AUDIT_HARDWARE_WORM")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_BACKEND")
        if backend is None:
            backend = str(nested.get("backend") or "fake")

        allow_live = nested.get("allow_live", False)
        env_l = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        endpoint = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_URL")
        if endpoint is None:
            endpoint = str(nested.get("endpoint_url") or "")

        token = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_TOKEN")
        if token is None:
            token = str(nested.get("token") or "")

        prefix = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_PREFIX")
        if prefix is None:
            prefix = str(nested.get("prefix") or "kerros/audit_worm/")

        strict = nested.get("strict", False)
        env_s = os.environ.get("KERROS_AUDIT_HARDWARE_WORM_STRICT")
        if env_s is not None:
            strict = _truthy(env_s)
        else:
            strict = _truthy(strict)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            endpoint_url=str(endpoint or "").strip(),
            token=str(token or "").strip(),
            prefix=str(prefix or "kerros/audit_worm/"),
            strict=bool(strict),
        )


@dataclass
class HardwareWormMirror:
    """Post-seal mirror helper."""

    cfg: HardwareWormConfig
    appliance: HardwareWormAppliance

    def mirror_segment(self, segment_path: Path, *, segment: int = 0) -> dict[str, Any]:
        if not self.cfg.enabled:
            return {"ok": False, "skipped": True, "error": "hardware WORM disabled"}
        path = Path(segment_path)
        if not path.is_file():
            out = {"ok": False, "error": f"missing segment: {path}"}
            if self.cfg.strict:
                raise HardwareWormError(out["error"])
            return out
        key = f"{self.cfg.prefix.rstrip('/')}/{path.name}"
        try:
            body = path.read_bytes()
            result = self.appliance.put_object(
                key, body, meta={"segment": segment, "source": str(path)}
            )
            return {"ok": True, **result}
        except Exception as exc:
            if self.cfg.strict:
                raise
            return {"ok": False, "error": str(exc)}

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.cfg.enabled,
            "backend": self.cfg.backend,
            "prefix": self.cfg.prefix,
            "appliance": self.appliance.stats(),
        }


def build_hardware_worm_mirror(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    appliance: HardwareWormAppliance | None = None,
) -> HardwareWormMirror | None:
    hw = HardwareWormConfig.from_mapping(cfg)
    if not hw.enabled:
        return None
    if appliance is not None:
        app = appliance
    elif hw.backend in ("http", "appliance"):
        app = SoftHttpHardwareWormAppliance(
            endpoint_url=hw.endpoint_url,
            token=hw.token,
            allow_live=hw.allow_live,
        )
    else:
        app = FakeHardwareWormAppliance()
    return HardwareWormMirror(cfg=hw, appliance=app)
