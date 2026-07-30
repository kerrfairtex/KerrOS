"""
runtime/distro_public_mirror.py
===============================
Public apt/yum mirror publish foundation (ADR-047).

Default-off. Stages a public-mirror *intent* and Fake-publishes indexes.
Soft rsync/HTTP to a configured public URL only when allow_public.
Never pushes to real public mirrors by default.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.nats_supercluster import _truthy


class PublicMirrorError(RuntimeError):
    """Public mirror publish failed."""


def rsync_available() -> bool:
    return bool(shutil.which("rsync"))


@dataclass
class PublicMirrorConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | rsync | http
    staging_dir: str = "deploy/packaging/public"
    public_url: str = ""
    token: str = ""
    allow_write: bool = False
    allow_public: bool = False  # explicit gate for public push

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "PublicMirrorConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        staging = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_DIR")
        if staging is None:
            staging = str(data.get("staging_dir") or "deploy/packaging/public")
        path = Path(staging)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        public_url = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_URL")
        if public_url is None:
            public_url = str(data.get("public_url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_public = data.get("allow_public", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_PUBLIC_MIRROR_PUSH")
        if env_p is not None:
            allow_public = _truthy(env_p)
        else:
            allow_public = _truthy(allow_public)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            staging_dir=str(path),
            public_url=str(public_url or "").strip(),
            token=str(token or "").strip(),
            allow_write=bool(allow_write),
            allow_public=bool(allow_public),
        )


@dataclass
class PublicMirrorPublisher:
    """Stage and optionally push public apt/yum mirror content."""

    cfg: PublicMirrorConfig
    _publishes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def stage(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise PublicMirrorError("public mirror disabled")
        if not self.cfg.allow_write:
            return {
                "ok": False,
                "skipped": True,
                "error": "write disabled",
                "public_url": self.cfg.public_url,
            }
        root = Path(self.cfg.staging_dir)
        apt = root / "apt" / "dists" / "stable" / "main" / "binary-all"
        yum = root / "yum" / "repodata"
        apt.mkdir(parents=True, exist_ok=True)
        yum.mkdir(parents=True, exist_ok=True)
        packages = apt / "Packages"
        packages.write_text("# Public mirror foundation index\n", encoding="utf-8")
        primary = yum / "primary.xml"
        primary.write_text(
            '<?xml version="1.0"?><metadata packages="0"/>\n', encoding="utf-8"
        )
        meta = root / "PUBLIC_MIRROR.json"
        meta.write_text(
            json.dumps(
                {
                    "public": False,
                    "url": self.cfg.public_url,
                    "note": "staged only — not published",
                    "at": time.time(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "ok": True,
            "written": [str(packages), str(primary), str(meta)],
            "at": time.time(),
        }

    def publish(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise PublicMirrorError("public mirror disabled")
        if self.cfg.allow_write:
            self.stage()
        staging = Path(self.cfg.staging_dir)
        if not self.cfg.allow_public:
            out = {
                "ok": True,
                "dry_run": True,
                "public": False,
                "staging": str(staging),
                "public_url": self.cfg.public_url,
                "note": "public push gated — set allow_public explicitly",
            }
            with self._lock:
                self._publishes += 1
                self._last = dict(out)
            return out
        if not self.cfg.public_url:
            raise PublicMirrorError("public_url required when allow_public")
        if self.cfg.backend == "rsync":
            if not rsync_available():
                raise PublicMirrorError("rsync not installed")
            proc = subprocess.run(
                [
                    "rsync",
                    "-az",
                    "--delete",
                    str(staging).rstrip("/") + "/",
                    self.cfg.public_url,
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )
            out = {
                "ok": proc.returncode == 0,
                "backend": "rsync",
                "public": True,
                "returncode": proc.returncode,
                "stderr": proc.stderr.decode("utf-8", errors="replace")[:300],
                "note": "soft public rsync — contract-funded mirrors only",
            }
        elif self.cfg.backend == "http":
            body = json.dumps(
                {"staging": str(staging), "at": time.time(), "public": True}
            ).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "kerros-public-mirror/1.0",
            }
            if self.cfg.token:
                headers["Authorization"] = f"Bearer {self.cfg.token}"
            req = Request(self.cfg.public_url, data=body, headers=headers, method="PUT")
            try:
                with urlopen(req, timeout=30) as resp:
                    _ = resp.read(256)
                out = {
                    "ok": True,
                    "backend": "http",
                    "public": True,
                    "note": "soft public HTTP PUT — contract-funded mirrors only",
                }
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                raise PublicMirrorError(f"public HTTP publish failed: {exc}") from exc
        else:
            out = {
                "ok": True,
                "backend": "fake",
                "public": False,
                "staging": str(staging),
                "public_url": self.cfg.public_url,
                "note": "Fake public publish — no bytes transferred",
            }
        with self._lock:
            self._publishes += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "public_url": self.cfg.public_url,
                "allow_write": self.cfg.allow_write,
                "allow_public": self.cfg.allow_public,
                "rsync": rsync_available(),
                "publishes": self._publishes,
                "last": dict(self._last),
            }


def build_public_mirror(
    cfg: Optional[Mapping[str, Any] | PublicMirrorConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[PublicMirrorPublisher]:
    if isinstance(cfg, PublicMirrorConfig):
        resolved = cfg
    else:
        resolved = PublicMirrorConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return PublicMirrorPublisher(cfg=resolved)
