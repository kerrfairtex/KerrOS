"""
runtime/actor_mesh_tls.py
========================
Optional stdlib TLS / mTLS for SocketActorBackend (ADR-023).

Default-off. Builds ``ssl.SSLContext`` from PEM paths; no hard crypto deps.
Production CA rotation and proxy-termination remain operator concerns.
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
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

        return cls(
            enabled=bool(enabled),
            ca_file=_path("ca_file", "KERROS_ACTOR_MESH_TLS_CA"),
            cert_file=_path("cert_file", "KERROS_ACTOR_MESH_TLS_CERT"),
            key_file=_path("key_file", "KERROS_ACTOR_MESH_TLS_KEY"),
            require_client_cert=bool(require),
            check_hostname=bool(check_hn),
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
