"""
runtime/actor_mesh_tls.py
========================
Optional stdlib TLS / mTLS for SocketActorBackend (ADR-023) + CA reload
foundation (ADR-028).

Default-off. Builds ``ssl.SSLContext`` from PEM paths; no hard crypto deps.
``ReloadingTlsHolder`` rebuilds contexts when PEM mtimes change.
"""

from __future__ import annotations

import os
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


class MeshTlsError(RuntimeError):
    """TLS config / context build failed."""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class MeshTlsConfig:
    enabled: bool = False
    ca_file: str = ""
    cert_file: str = ""
    key_file: str = ""
    require_client_cert: bool = False  # mTLS when True
    check_hostname: bool = False
    reload: bool = False  # ADR-028
    reload_interval_s: float = 0.0

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "MeshTlsConfig":
        data = dict(raw or {})

        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_TLS")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        def _path(key: str, env_key: str) -> str:
            env_v = os.environ.get(env_key)
            if env_v is not None:
                text = str(env_v).strip()
            else:
                text = str(data.get(key) or "").strip()
            if not text:
                return ""
            path = Path(text)
            if not path.is_absolute() and base is not None:
                path = Path(base) / path
            return str(path)

        require = data.get("require_client_cert", False)
        env_r = os.environ.get("KERROS_ACTOR_MESH_TLS_MTLS")
        if env_r is not None:
            require = _truthy(env_r)
        else:
            require = _truthy(require)

        check_hn = data.get("check_hostname", False)
        env_c = os.environ.get("KERROS_ACTOR_MESH_TLS_CHECK_HOSTNAME")
        if env_c is not None:
            check_hn = _truthy(env_c)
        else:
            check_hn = _truthy(check_hn)

        reload = data.get("reload", False)
        env_rel = os.environ.get("KERROS_ACTOR_MESH_TLS_RELOAD")
        if env_rel is not None:
            reload = _truthy(env_rel)
        else:
            reload = _truthy(reload)

        interval = data.get("reload_interval_s", 0.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_TLS_RELOAD_INTERVAL")
        if env_i is not None:
            interval = float(env_i)

        return cls(
            enabled=bool(enabled),
            ca_file=_path("ca_file", "KERROS_ACTOR_MESH_TLS_CA"),
            cert_file=_path("cert_file", "KERROS_ACTOR_MESH_TLS_CERT"),
            key_file=_path("key_file", "KERROS_ACTOR_MESH_TLS_KEY"),
            require_client_cert=bool(require),
            check_hostname=bool(check_hn),
            reload=bool(reload),
            reload_interval_s=max(0.0, float(interval or 0.0)),
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.cert_file or not self.key_file:
            raise MeshTlsError(
                "actor mesh TLS requires cert_file and key_file "
                "(or KERROS_ACTOR_MESH_TLS_CERT / _KEY)"
            )
        for label, path in (
            ("cert_file", self.cert_file),
            ("key_file", self.key_file),
            ("ca_file", self.ca_file),
        ):
            if path and not Path(path).is_file():
                raise MeshTlsError(f"actor mesh TLS {label} not found: {path}")
        if self.require_client_cert and not self.ca_file:
            raise MeshTlsError(
                "mTLS (require_client_cert) needs ca_file / KERROS_ACTOR_MESH_TLS_CA"
            )


def build_server_ssl_context(cfg: MeshTlsConfig) -> ssl.SSLContext:
    cfg.validate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cfg.cert_file, keyfile=cfg.key_file)
    if cfg.ca_file:
        ctx.load_verify_locations(cafile=cfg.ca_file)
    if cfg.require_client_cert:
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def build_client_ssl_context(cfg: MeshTlsConfig) -> ssl.SSLContext:
    cfg.validate()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = bool(cfg.check_hostname)
    if cfg.ca_file:
        ctx.load_verify_locations(cafile=cfg.ca_file)
        ctx.verify_mode = ssl.CERT_REQUIRED if cfg.check_hostname else ssl.CERT_OPTIONAL
    else:
        ctx.verify_mode = ssl.CERT_NONE
    if cfg.cert_file and cfg.key_file:
        ctx.load_cert_chain(certfile=cfg.cert_file, keyfile=cfg.key_file)
    return ctx


def pem_mtimes(cfg: MeshTlsConfig) -> dict[str, float]:
    """Return mtimes for configured PEM paths (missing → 0.0)."""
    out: dict[str, float] = {}
    for key, path in (
        ("ca_file", cfg.ca_file),
        ("cert_file", cfg.cert_file),
        ("key_file", cfg.key_file),
    ):
        if not path:
            out[key] = 0.0
            continue
        try:
            out[key] = float(Path(path).stat().st_mtime)
        except OSError:
            out[key] = 0.0
    return out


def contexts_stale(cfg: MeshTlsConfig, last: Mapping[str, float]) -> bool:
    now = pem_mtimes(cfg)
    for key, ts in now.items():
        if float(last.get(key) or 0.0) != ts:
            return True
    return False


def reload_ssl_contexts(
    cfg: MeshTlsConfig,
) -> tuple[ssl.SSLContext, ssl.SSLContext, dict[str, float]]:
    """Rebuild server+client contexts; return contexts + current mtimes."""
    server = build_server_ssl_context(cfg)
    client = build_client_ssl_context(cfg)
    return server, client, pem_mtimes(cfg)


@dataclass
class ReloadingTlsHolder:
    """
    Holds SSL contexts and rebuilds them when PEM mtimes change (ADR-028).

    Existing connections keep the old context; new accept/dial use the latest.
    """

    cfg: MeshTlsConfig
    server_context: ssl.SSLContext | None = None
    client_context: ssl.SSLContext | None = None
    _mtimes: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _reloads: int = 0
    _last_check: float = 0.0

    @classmethod
    def from_config(cls, cfg: MeshTlsConfig) -> "ReloadingTlsHolder":
        holder = cls(cfg=cfg)
        if cfg.enabled:
            holder.reload(force=True)
        return holder

    def reload(self, *, force: bool = False) -> bool:
        with self._lock:
            if not self.cfg.enabled:
                return False
            if not force and not contexts_stale(self.cfg, self._mtimes):
                return False
            server, client, mtimes = reload_ssl_contexts(self.cfg)
            self.server_context = server
            self.client_context = client
            self._mtimes = mtimes
            self._reloads += 1
            self._last_check = time.time()
            return True

    def maybe_reload(self) -> bool:
        """Reload if enabled and interval elapsed (interval 0 → check every call)."""
        if not self.cfg.enabled or not self.cfg.reload:
            return False
        now = time.time()
        interval = float(self.cfg.reload_interval_s or 0.0)
        with self._lock:
            if interval > 0 and (now - self._last_check) < interval:
                return False
            self._last_check = now
        return self.reload(force=False)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "reload": self.cfg.reload,
                "reloads": self._reloads,
                "mtimes": dict(self._mtimes),
                "interval_s": self.cfg.reload_interval_s,
            }
