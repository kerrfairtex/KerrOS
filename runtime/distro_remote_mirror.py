"""
runtime/distro_remote_mirror.py
===============================
Remote apt/yum mirror push foundation (ADR-043).

Default-off. Fake remote mirror for CI; soft rsync / scp / HTTP PUT when
``allow_remote``. Never uploads to public mirrors by default.
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
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.nats_supercluster import _truthy


class RemoteMirrorError(RuntimeError):
    """Remote mirror publish failed."""


def rsync_available() -> bool:
    return bool(shutil.which("rsync"))


def scp_available() -> bool:
    return bool(shutil.which("scp"))


@runtime_checkable
class RemoteMirrorBackend(Protocol):
    def push(self, staging: Path, *, remote_url: str) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeRemoteMirror:
    """Record push intent without network I/O."""

    _pushes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)

    def push(self, staging: Path, *, remote_url: str) -> dict[str, Any]:
        out = {
            "ok": True,
            "backend": "fake",
            "staging": str(staging),
            "remote_url": remote_url,
            "files": sum(1 for _ in staging.rglob("*") if _.is_file()) if staging.exists() else 0,
            "at": time.time(),
            "note": "Fake remote push — no bytes transferred",
        }
        self._pushes += 1
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake", "pushes": self._pushes, "last": dict(self._last)}


@dataclass
class SoftRsyncMirror:
    """Soft ``rsync -az`` when allow_remote + rsync present."""

    allow_remote: bool = False
    extra_args: list[str] = field(default_factory=list)
    _shadow: FakeRemoteMirror = field(default_factory=FakeRemoteMirror)
    _last: dict[str, Any] = field(default_factory=dict)

    def push(self, staging: Path, *, remote_url: str) -> dict[str, Any]:
        if not self.allow_remote or not rsync_available() or not remote_url.strip():
            out = self._shadow.push(staging, remote_url=remote_url)
            out["dry_run"] = True
            out["rsync"] = rsync_available()
            self._last = dict(out)
            return out
        cmd = ["rsync", "-az", "--delete"] + list(self.extra_args)
        src = str(staging).rstrip("/") + "/"
        cmd.extend([src, remote_url])
        proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        out = {
            "ok": proc.returncode == 0,
            "backend": "rsync",
            "remote_url": remote_url,
            "returncode": proc.returncode,
            "stderr": proc.stderr.decode("utf-8", errors="replace")[:300],
            "at": time.time(),
        }
        self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "rsync",
            "allow_remote": self.allow_remote,
            "available": rsync_available(),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class SoftHttpMirror:
    """Soft HTTP PUT of a manifest JSON when allow_remote."""

    allow_remote: bool = False
    token: str = ""
    timeout_s: float = 30.0
    _shadow: FakeRemoteMirror = field(default_factory=FakeRemoteMirror)
    _last: dict[str, Any] = field(default_factory=dict)

    def push(self, staging: Path, *, remote_url: str) -> dict[str, Any]:
        if not self.allow_remote or not remote_url.strip():
            out = self._shadow.push(staging, remote_url=remote_url)
            out["dry_run"] = True
            self._last = dict(out)
            return out
        manifest = {
            "staging": str(staging),
            "files": [
                str(p.relative_to(staging))
                for p in staging.rglob("*")
                if p.is_file()
            ][:200]
            if staging.exists()
            else [],
            "at": time.time(),
            "note": "manifest-only HTTP PUT — not a full mirror sync",
        }
        body = json.dumps(manifest).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "kerros-remote-mirror/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(remote_url, data=body, headers=headers, method="PUT")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                _ = resp.read(256)
            out = {
                "ok": True,
                "backend": "http",
                "remote_url": remote_url,
                "files": len(manifest["files"]),
                "at": time.time(),
            }
            self._last = dict(out)
            return out
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RemoteMirrorError(f"HTTP mirror push failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "http",
            "allow_remote": self.allow_remote,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class RemoteMirrorConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | rsync | http
    staging_dir: str = "deploy/packaging/repos"
    remote_url: str = ""
    token: str = ""
    allow_remote: bool = False
    allow_write: bool = False

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "RemoteMirrorConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        staging = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_DIR")
        if staging is None:
            staging = str(data.get("staging_dir") or "deploy/packaging/repos")
        path = Path(staging)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        remote_url = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_URL")
        if remote_url is None:
            remote_url = str(data.get("remote_url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        allow_remote = data.get("allow_remote", False)
        env_r = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_PUSH")
        if env_r is not None:
            allow_remote = _truthy(env_r)
        else:
            allow_remote = _truthy(allow_remote)

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_REMOTE_MIRROR_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            staging_dir=str(path),
            remote_url=str(remote_url or "").strip(),
            token=str(token or "").strip(),
            allow_remote=bool(allow_remote),
            allow_write=bool(allow_write),
        )


@dataclass
class RemoteMirrorPublisher:
    """Push staged apt/yum trees to a remote mirror (gated)."""

    cfg: RemoteMirrorConfig
    backend: RemoteMirrorBackend = field(default_factory=FakeRemoteMirror)
    _pushes: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def stage_marker(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise RemoteMirrorError("remote mirror disabled")
        if not self.cfg.allow_write:
            return {"ok": False, "skipped": True, "error": "write disabled"}
        root = Path(self.cfg.staging_dir)
        root.mkdir(parents=True, exist_ok=True)
        marker = root / "MIRROR_READY"
        marker.write_text(f"ready_at={time.time()}\n", encoding="utf-8")
        return {"ok": True, "path": str(marker)}

    def push(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise RemoteMirrorError("remote mirror disabled")
        if self.cfg.allow_write:
            self.stage_marker()
        staging = Path(self.cfg.staging_dir)
        out = self.backend.push(staging, remote_url=self.cfg.remote_url)
        with self._lock:
            self._pushes += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "remote_url": self.cfg.remote_url,
                "allow_remote": self.cfg.allow_remote,
                "allow_write": self.cfg.allow_write,
                "rsync": rsync_available(),
                "scp": scp_available(),
                "pushes": self._pushes,
                "last": dict(self._last),
                "transport": self.backend.stats(),
            }


def build_remote_mirror(
    cfg: Optional[Mapping[str, Any] | RemoteMirrorConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[RemoteMirrorPublisher]:
    if isinstance(cfg, RemoteMirrorConfig):
        resolved = cfg
    else:
        resolved = RemoteMirrorConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    if resolved.backend == "rsync":
        backend: RemoteMirrorBackend = SoftRsyncMirror(
            allow_remote=resolved.allow_remote
        )
    elif resolved.backend == "http":
        backend = SoftHttpMirror(
            allow_remote=resolved.allow_remote, token=resolved.token
        )
    else:
        backend = FakeRemoteMirror()
    return RemoteMirrorPublisher(cfg=resolved, backend=backend)
