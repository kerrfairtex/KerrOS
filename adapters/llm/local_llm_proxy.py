"""
adapters/llm/local_llm_proxy.py
================================
Auth/TLS edge proxy foundation for local LLMs (C-19 / ADR-049).

Default-off. Fake-plans a loopback auth/TLS front for Ollama/vLLM.
Soft probes for caddy/nginx/openssl when gated. Never claims
``production_tls`` or ``public_bind_ok`` without explicit allow flags
plus a live confirm — not a production edge seal.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class LocalLlmProxyError(RuntimeError):
    """Local LLM proxy planning failed."""


def caddy_available() -> bool:
    return bool(shutil.which("caddy"))


def nginx_available() -> bool:
    return bool(shutil.which("nginx"))


def openssl_available() -> bool:
    return bool(shutil.which("openssl"))


@dataclass
class LocalLlmProxyConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | caddy | nginx
    upstream: str = "http://127.0.0.1:8000"
    listen: str = "127.0.0.1:8443"
    token: str = ""
    allow_tls: bool = False
    allow_non_loopback: bool = False
    allow_live: bool = False
    template_dir: str = "deploy/vllm/proxy"

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "LocalLlmProxyConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_LOCAL_LLM_PROXY")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_LOCAL_LLM_PROXY_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        upstream = os.environ.get("KERROS_LOCAL_LLM_PROXY_UPSTREAM")
        if upstream is None:
            upstream = str(data.get("upstream") or "http://127.0.0.1:8000")

        listen = os.environ.get("KERROS_LOCAL_LLM_PROXY_LISTEN")
        if listen is None:
            listen = str(data.get("listen") or "127.0.0.1:8443")

        token = os.environ.get("KERROS_LOCAL_LLM_PROXY_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        allow_tls = data.get("allow_tls", False)
        env_t = os.environ.get("KERROS_LOCAL_LLM_PROXY_TLS")
        if env_t is not None:
            allow_tls = _truthy(env_t)
        else:
            allow_tls = _truthy(allow_tls)

        allow_non_loopback = data.get("allow_non_loopback", False)
        env_n = os.environ.get("KERROS_LOCAL_LLM_PROXY_NON_LOOPBACK")
        if env_n is not None:
            allow_non_loopback = _truthy(env_n)
        else:
            allow_non_loopback = _truthy(allow_non_loopback)

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_LOCAL_LLM_PROXY_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        template_dir = os.environ.get("KERROS_LOCAL_LLM_PROXY_DIR")
        if template_dir is None:
            template_dir = str(data.get("template_dir") or "deploy/vllm/proxy")
        path = Path(template_dir)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            upstream=str(upstream or "").strip(),
            listen=str(listen or "").strip(),
            token=str(token or "").strip(),
            allow_tls=bool(allow_tls),
            allow_non_loopback=bool(allow_non_loopback),
            allow_live=bool(allow_live),
            template_dir=str(path),
        )


def _is_loopback_listen(listen: str) -> bool:
    host = (listen or "").rsplit(":", 1)[0].strip("[]")
    return host in ("127.0.0.1", "localhost", "::1", "")


@dataclass
class LocalLlmProxyPlanner:
    """Plan (and optionally soft-probe) an auth/TLS edge for local LLMs."""

    cfg: LocalLlmProxyConfig
    _plans: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def plan(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise LocalLlmProxyError("local LLM proxy disabled")
        loopback = _is_loopback_listen(self.cfg.listen)
        public_bind_ok = bool(self.cfg.allow_non_loopback and not loopback)
        production_tls = False  # never silent — needs live confirm below
        out: dict[str, Any] = {
            "ok": True,
            "backend": self.cfg.backend,
            "upstream": self.cfg.upstream,
            "listen": self.cfg.listen,
            "auth": "bearer" if self.cfg.token else "none",
            "loopback": loopback,
            "public_bind_ok": public_bind_ok if not loopback else False,
            "production_tls": production_tls,
            "tls_intent": bool(self.cfg.allow_tls),
            "template_dir": self.cfg.template_dir,
            "dry_run": True,
            "note": "Fake edge plan — not a production TLS/auth seal",
            "at": time.time(),
        }
        if self.cfg.allow_live and self.cfg.allow_tls:
            tools = {
                "caddy": caddy_available(),
                "nginx": nginx_available(),
                "openssl": openssl_available(),
            }
            out["tools"] = tools
            out["dry_run"] = False
            # Soft probe only — still not a production seal without contract.
            out["production_tls"] = False
            out["note"] = (
                "Soft tool probe — production_tls stays False without "
                "contract-funded edge cert custody"
            )
        with self._lock:
            self._plans += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "listen": self.cfg.listen,
                "upstream": self.cfg.upstream,
                "allow_tls": self.cfg.allow_tls,
                "allow_non_loopback": self.cfg.allow_non_loopback,
                "allow_live": self.cfg.allow_live,
                "plans": self._plans,
                "last": dict(self._last),
            }


def build_local_llm_proxy(
    cfg: Optional[Mapping[str, Any] | LocalLlmProxyConfig] = None,
    *,
    base: Optional[Path] = None,
) -> Optional[LocalLlmProxyPlanner]:
    if isinstance(cfg, LocalLlmProxyConfig):
        resolved = cfg
    else:
        resolved = LocalLlmProxyConfig.from_mapping(cfg, base=base)
    if not resolved.enabled:
        return None
    return LocalLlmProxyPlanner(cfg=resolved)
