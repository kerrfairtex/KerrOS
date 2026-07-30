"""
runtime/nats_supercluster_control.py
====================================
Live Supercluster *control-plane* foundation (ADR-032).

Default-off. Can write rendered NATS config snippets under ``config_dir``,
soft-probe monitoring URLs (healthz/varz), and soft-probe ``nats-server
--signal reload`` when allowed. Does **not** start NATS brokers — CI uses
an in-memory backend.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import URLError
from urllib.request import Request, urlopen

from runtime.nats_supercluster import _truthy
from runtime.nats_supercluster_ops import SuperclusterOps


class SuperclusterControlError(RuntimeError):
    """Control-plane operation failed."""


@runtime_checkable
class ControlPlaneBackend(Protocol):
    def write_config(self, name: str, body: str) -> str: ...

    def list_configs(self) -> list[str]: ...

    def record_reload(self, target: str) -> dict[str, Any]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class InMemoryControlPlaneBackend:
    """CI-safe control-plane backend (no disk / no signals)."""

    _files: dict[str, str] = field(default_factory=dict)
    _reloads: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def write_config(self, name: str, body: str) -> str:
        key = str(name or "cluster").strip() or "cluster"
        with self._lock:
            self._files[key] = str(body)
        return f"mem://{key}"

    def list_configs(self) -> list[str]:
        with self._lock:
            return sorted(self._files)

    def record_reload(self, target: str) -> dict[str, Any]:
        item = {"target": target, "ok": True, "at": time.time(), "backend": "memory"}
        with self._lock:
            self._reloads.append(item)
        return dict(item)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "memory",
                "configs": len(self._files),
                "reloads": len(self._reloads),
            }


@dataclass
class FileControlPlaneBackend:
    """Writes config snippets under config_dir when allow_write."""

    config_dir: Path
    allow_write: bool = False
    _reloads: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def write_config(self, name: str, body: str) -> str:
        if not self.allow_write:
            raise SuperclusterControlError("control-plane write disabled")
        key = str(name or "cluster").strip() or "cluster"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        path = self.config_dir / f"{safe}.conf"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(str(body), encoding="utf-8")
        return str(path)

    def list_configs(self) -> list[str]:
        if not self.config_dir.is_dir():
            return []
        return sorted(p.name for p in self.config_dir.glob("*.conf"))

    def record_reload(self, target: str) -> dict[str, Any]:
        item = {"target": target, "ok": True, "at": time.time(), "backend": "file"}
        with self._lock:
            self._reloads.append(item)
        return dict(item)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "file",
                "config_dir": str(self.config_dir),
                "allow_write": self.allow_write,
                "configs": len(self.list_configs()),
                "reloads": len(self._reloads),
            }


def probe_monitor_url(url: str, *, timeout_s: float = 2.0) -> dict[str, Any]:
    """Soft GET of a NATS monitoring URL. Never raises."""
    target = str(url or "").strip()
    if not target:
        return {"ok": False, "skipped": True, "error": "url required"}
    try:
        req = Request(target, method="GET", headers={"User-Agent": "kerros-sc-cp/1"})
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            body = resp.read(4096)
            return {
                "ok": True,
                "url": target,
                "status": getattr(resp, "status", 200),
                "bytes": len(body),
            }
    except (URLError, OSError, ValueError) as exc:
        return {"ok": False, "url": target, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "url": target, "error": str(exc)}


def soft_nats_signal_reload(
    *,
    bin_name: str = "nats-server",
    pid: str = "",
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Soft ``nats-server --signal reload[=pid]`` probe. Never raises."""
    path = shutil.which(bin_name)
    if not path:
        return {"ok": False, "skipped": True, "error": f"{bin_name} not on PATH"}
    signal = f"reload={pid}" if str(pid or "").strip() else "reload"
    try:
        proc = subprocess.run(
            [path, "--signal", signal],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr": (proc.stderr or "")[-1000:],
            "signal": signal,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@dataclass
class SuperclusterControlConfig:
    enabled: bool = False
    config_dir: str = "data/supercluster_cp"
    allow_write: bool = False
    allow_monitor_probe: bool = False
    monitor_urls: list[str] = field(default_factory=list)
    monitor_timeout_s: float = 2.0
    allow_signal_reload: bool = False
    nats_server_bin: str = "nats-server"
    backend: str = "file"  # file | memory

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "SuperclusterControlConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        config_dir = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_DIR")
        if config_dir is None:
            config_dir = str(data.get("config_dir") or "data/supercluster_cp")
        path = Path(config_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        allow_write = data.get("allow_write", False)
        env_w = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_WRITE")
        if env_w is not None:
            allow_write = _truthy(env_w)
        else:
            allow_write = _truthy(allow_write)

        allow_mon = data.get("allow_monitor_probe", False)
        env_m = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_MONITOR")
        if env_m is not None:
            allow_mon = _truthy(env_m)
        else:
            allow_mon = _truthy(allow_mon)

        urls_raw = data.get("monitor_urls") or []
        env_u = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_MONITOR_URLS")
        if env_u is not None:
            urls = [u.strip() for u in env_u.split(",") if u.strip()]
        elif isinstance(urls_raw, str):
            urls = [u.strip() for u in urls_raw.split(",") if u.strip()]
        else:
            urls = [str(u).strip() for u in urls_raw if str(u).strip()]

        timeout = data.get("monitor_timeout_s", 2.0)
        env_t = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_MONITOR_TIMEOUT")
        if env_t is not None:
            timeout = float(env_t)

        allow_sig = data.get("allow_signal_reload", False)
        env_s = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_SIGNAL")
        if env_s is not None:
            allow_sig = _truthy(env_s)
        else:
            allow_sig = _truthy(allow_sig)

        backend = os.environ.get("KERROS_ACTOR_MESH_SUPERCLUSTER_CP_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "file")

        return cls(
            enabled=bool(enabled),
            config_dir=str(path),
            allow_write=bool(allow_write),
            allow_monitor_probe=bool(allow_mon),
            monitor_urls=urls,
            monitor_timeout_s=max(0.1, float(timeout or 2.0)),
            allow_signal_reload=bool(allow_sig),
            nats_server_bin=str(
                os.environ.get("KERROS_ACTOR_MESH_NATS_SERVER_BIN")
                or data.get("nats_server_bin")
                or "nats-server"
            ).strip()
            or "nats-server",
            backend=str(backend or "file").strip().lower() or "file",
        )


@dataclass
class SuperclusterControlPlane:
    """Control-plane facade over ops snippets + backend."""

    cfg: SuperclusterControlConfig
    ops: SuperclusterOps | None = None
    backend: ControlPlaneBackend = field(default_factory=InMemoryControlPlaneBackend)
    _writes: list[str] = field(default_factory=list)
    _last_monitors: list[dict[str, Any]] = field(default_factory=list)
    _last_signal: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def publish_config(self) -> dict[str, Any]:
        """Render ops snippets and write via backend (when allowed / memory)."""
        if self.ops is None:
            raise SuperclusterControlError("ops required for publish_config")
        snippets = self.ops.render_nats_snippets()
        body_parts = [
            f"# supercluster={snippets.get('name') or 'kerros'}",
            snippets.get("gateways") or "",
            snippets.get("leafnodes") or "",
        ]
        body = "\n\n".join(p for p in body_parts if p).strip() + "\n"
        name = snippets.get("name") or "kerros"
        if isinstance(self.backend, FileControlPlaneBackend) and not self.cfg.allow_write:
            # Still allow in-memory path when file write disabled.
            raise SuperclusterControlError("control-plane write disabled")
        path = self.backend.write_config(str(name), body)
        with self._lock:
            self._writes.append(path)
        return {"ok": True, "path": path, "bytes": len(body)}

    def probe_monitors(self) -> list[dict[str, Any]]:
        if not self.cfg.allow_monitor_probe:
            out = [{"ok": False, "skipped": True, "error": "monitor probe disabled"}]
            self._last_monitors = out
            return list(out)
        results = [
            probe_monitor_url(u, timeout_s=self.cfg.monitor_timeout_s)
            for u in self.cfg.monitor_urls
        ]
        if not results:
            results = [{"ok": False, "skipped": True, "error": "no monitor_urls"}]
        self._last_monitors = list(results)
        return list(results)

    def maybe_signal_reload(self, *, pid: str = "") -> dict[str, Any]:
        if not self.cfg.allow_signal_reload:
            out = {"ok": False, "skipped": True, "error": "signal reload disabled"}
            self._last_signal = out
            return out
        # Always record via backend for ledger; soft real signal when bin present.
        ledger = self.backend.record_reload(pid or "default")
        soft = soft_nats_signal_reload(
            bin_name=self.cfg.nats_server_bin, pid=pid
        )
        out = {"ledger": ledger, **soft}
        self._last_signal = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_write": self.cfg.allow_write,
                "writes": len(self._writes),
                "last_write": self._writes[-1] if self._writes else "",
                "monitor_urls": list(self.cfg.monitor_urls),
                "last_monitors": list(self._last_monitors),
                "last_signal": dict(self._last_signal),
                "backend_stats": self.backend.stats(),
            }


def build_supercluster_control_plane(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    ops: SuperclusterOps | None = None,
    backend: ControlPlaneBackend | None = None,
    base: Optional[Path] = None,
) -> SuperclusterControlPlane | None:
    cp_cfg = SuperclusterControlConfig.from_mapping(cfg, base=base)
    if not cp_cfg.enabled:
        return None
    if backend is not None:
        be = backend
    elif cp_cfg.backend in ("memory", "mem", "inmemory"):
        be = InMemoryControlPlaneBackend()
    else:
        be = FileControlPlaneBackend(
            config_dir=Path(cp_cfg.config_dir),
            allow_write=cp_cfg.allow_write,
        )
    return SuperclusterControlPlane(cfg=cp_cfg, ops=ops, backend=be)
