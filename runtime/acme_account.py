"""
runtime/acme_account.py
=======================
ACME account registry foundation (ADR-031).

Default-off. Stores a local account record (contact, directory URL, kid
stub) under ``account_dir``. Dry-run registration does **not** talk to
Let's Encrypt; optional soft directory probe via urllib when enabled.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class AcmeAccountError(RuntimeError):
    """ACME account registry failed."""


DEFAULT_STAGING_DIRECTORY = (
    "https://acme-staging-v02.api.letsencrypt.org/directory"
)


@dataclass
class AcmeAccountConfig:
    enabled: bool = False
    directory_url: str = DEFAULT_STAGING_DIRECTORY
    contact_email: str = ""
    account_dir: str = "data/acme_account"
    dry_run: bool = True
    allow_directory_probe: bool = False
    probe_timeout_s: float = 5.0

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "AcmeAccountConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_ACCOUNT")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        directory = os.environ.get("KERROS_ACTOR_MESH_ACME_DIRECTORY")
        if directory is None:
            directory = str(data.get("directory_url") or DEFAULT_STAGING_DIRECTORY)

        email = os.environ.get("KERROS_ACTOR_MESH_ACME_CONTACT")
        if email is None:
            email = str(data.get("contact_email") or "")

        account_dir = os.environ.get("KERROS_ACTOR_MESH_ACME_ACCOUNT_DIR")
        if account_dir is None:
            account_dir = str(data.get("account_dir") or "data/acme_account")
        path = Path(account_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        dry_raw = data.get("dry_run", True)
        env_d = os.environ.get("KERROS_ACTOR_MESH_ACME_ACCOUNT_DRY_RUN")
        if env_d is not None:
            dry = _truthy(env_d)
        elif isinstance(dry_raw, bool):
            dry = dry_raw
        else:
            dry = _truthy(dry_raw) if dry_raw is not None else True

        probe = data.get("allow_directory_probe", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_ACME_DIRECTORY_PROBE")
        if env_p is not None:
            probe = _truthy(env_p)
        else:
            probe = _truthy(probe)

        timeout = data.get("probe_timeout_s", 5.0)
        env_t = os.environ.get("KERROS_ACTOR_MESH_ACME_DIRECTORY_TIMEOUT")
        if env_t is not None:
            timeout = float(env_t)

        return cls(
            enabled=bool(enabled),
            directory_url=str(directory or DEFAULT_STAGING_DIRECTORY).strip()
            or DEFAULT_STAGING_DIRECTORY,
            contact_email=str(email or "").strip(),
            account_dir=str(path),
            dry_run=bool(dry),
            allow_directory_probe=bool(probe),
            probe_timeout_s=max(0.5, float(timeout or 5.0)),
        )


def probe_acme_directory(
    directory_url: str,
    *,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Soft GET of ACME directory JSON. Never raises."""
    url = str(directory_url or "").strip()
    if not url:
        return {"ok": False, "error": "directory_url required", "skipped": True}
    try:
        req = Request(url, method="GET", headers={"User-Agent": "kerros-acme-account/1"})
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 — operator-configured URL
            body = resp.read(65536)
            data = json.loads(body.decode("utf-8"))
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "keys": sorted(data.keys()) if isinstance(data, dict) else [],
                "newAccount": data.get("newAccount") if isinstance(data, dict) else None,
            }
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@dataclass
class AcmeAccountRegistry:
    """Local ACME account record store (JSON file)."""

    cfg: AcmeAccountConfig
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _record: dict[str, Any] | None = None
    _last_probe: dict[str, Any] = field(default_factory=dict)

    def _path(self) -> Path:
        return Path(self.cfg.account_dir) / "account.json"

    def load(self) -> dict[str, Any] | None:
        path = self._path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                with self._lock:
                    self._record = data
                return dict(data)
        except (OSError, json.JSONDecodeError):
            return None
        return None

    def register(self) -> dict[str, Any]:
        """
        Create/update local account stub.
        Live ACME newAccount is out of scope — dry_run always local unless
        allow_directory_probe only probes the directory endpoint.
        """
        if not self.cfg.enabled:
            raise AcmeAccountError("ACME account registry disabled")
        existing = self.load()
        if existing and existing.get("status") == "registered":
            return dict(existing)

        kid = f"local:{uuid.uuid4().hex}"
        record = {
            "kid": kid,
            "status": "registered" if self.cfg.dry_run else "pending_live",
            "dry_run": bool(self.cfg.dry_run),
            "directory_url": self.cfg.directory_url,
            "contact_email": self.cfg.contact_email,
            "created_at": time.time(),
            "note": "local stub — does not call ACME newAccount",
        }
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self._lock:
            self._record = dict(record)
        return dict(record)

    def maybe_probe_directory(self) -> dict[str, Any]:
        if not self.cfg.allow_directory_probe:
            out = {"ok": False, "skipped": True, "error": "directory probe disabled"}
            self._last_probe = out
            return out
        out = probe_acme_directory(
            self.cfg.directory_url, timeout_s=self.cfg.probe_timeout_s
        )
        self._last_probe = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rec = dict(self._record) if self._record else self.load()
            return {
                "enabled": self.cfg.enabled,
                "dry_run": self.cfg.dry_run,
                "directory_url": self.cfg.directory_url,
                "contact_email": self.cfg.contact_email,
                "account_dir": self.cfg.account_dir,
                "registered": bool(rec and rec.get("status") in ("registered", "pending_live")),
                "kid": (rec or {}).get("kid", ""),
                "last_probe": dict(self._last_probe),
            }


def build_acme_account_registry(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> AcmeAccountRegistry | None:
    account_cfg = AcmeAccountConfig.from_mapping(cfg, base=base)
    if not account_cfg.enabled:
        return None
    return AcmeAccountRegistry(cfg=account_cfg)
