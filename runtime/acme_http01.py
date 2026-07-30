"""
runtime/acme_http01.py
======================
ACME HTTP-01 challenge solver foundation (ADR-030).

Default-off. Serves ``/.well-known/acme-challenge/<token>`` from an
in-memory token store (stdlib ``http.server``). Does **not** register
ACME accounts or talk to Let's Encrypt — operators / certbot own issuance;
this answers challenges when enabled.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping, Optional
from urllib.parse import unquote


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class AcmeHttp01Error(RuntimeError):
    """HTTP-01 solver failed."""


@dataclass
class AcmeHttp01Config:
    enabled: bool = False
    bind: str = "127.0.0.1"
    port: int = 0  # 0 = ephemeral bind
    path_prefix: str = "/.well-known/acme-challenge"

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeHttp01Config":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_HTTP01")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        bind = os.environ.get("KERROS_ACTOR_MESH_ACME_HTTP01_BIND")
        if bind is None:
            bind = str(data.get("bind") or "127.0.0.1")

        port = data.get("port", 0)
        env_p = os.environ.get("KERROS_ACTOR_MESH_ACME_HTTP01_PORT")
        if env_p is not None and str(env_p).strip().isdigit():
            port = int(env_p)

        prefix = os.environ.get("KERROS_ACTOR_MESH_ACME_HTTP01_PREFIX")
        if prefix is None:
            prefix = str(data.get("path_prefix") or "/.well-known/acme-challenge")

        return cls(
            enabled=bool(enabled),
            bind=str(bind or "127.0.0.1").strip() or "127.0.0.1",
            port=max(0, int(port)),  # 0 = ephemeral (tests / lab)
            path_prefix=str(prefix or "/.well-known/acme-challenge").rstrip("/")
            or "/.well-known/acme-challenge",
        )


@dataclass
class AcmeHttp01Solver:
    """In-memory HTTP-01 token responder."""

    cfg: AcmeHttp01Config
    _tokens: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _httpd: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    _hits: int = 0
    _misses: int = 0

    def put_challenge(self, token: str, key_authorization: str) -> None:
        tok = str(token or "").strip()
        if not tok:
            raise AcmeHttp01Error("token required")
        with self._lock:
            self._tokens[tok] = str(key_authorization or "")

    def clear_challenge(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(str(token or "").strip(), None)

    def get_challenge(self, token: str) -> str | None:
        with self._lock:
            return self._tokens.get(str(token or "").strip())

    def start(self) -> None:
        if not self.cfg.enabled:
            raise AcmeHttp01Error("ACME HTTP-01 solver disabled")
        if self._httpd is not None:
            return

        solver = self
        prefix = self.cfg.path_prefix

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                path = unquote(self.path.split("?", 1)[0])
                if not path.startswith(prefix + "/") and path != prefix:
                    self.send_response(404)
                    self.end_headers()
                    with solver._lock:
                        solver._misses += 1
                    return
                token = path[len(prefix) :].lstrip("/")
                body = solver.get_challenge(token)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    with solver._lock:
                        solver._misses += 1
                    return
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                with solver._lock:
                    solver._hits += 1

        self._httpd = ThreadingHTTPServer((self.cfg.bind, self.cfg.port), Handler)
        # Ephemeral port support: port 0 → update cfg.port from socket.
        if self.cfg.port == 0:
            self.cfg.port = int(self._httpd.server_address[1])

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="acme-http01",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def base_url(self) -> str:
        return f"http://{self.cfg.bind}:{self.cfg.port}{self.cfg.path_prefix}"

    def challenge_url(self, token: str) -> str:
        return f"{self.base_url}/{token}"

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "listening": self._httpd is not None,
                "bind": self.cfg.bind,
                "port": self.cfg.port,
                "path_prefix": self.cfg.path_prefix,
                "tokens": len(self._tokens),
                "hits": self._hits,
                "misses": self._misses,
                "base_url": self.base_url if self._httpd else "",
            }


def build_acme_http01_solver(
    cfg: Optional[Mapping[str, Any]] = None,
) -> AcmeHttp01Solver | None:
    http_cfg = AcmeHttp01Config.from_mapping(cfg)
    if not http_cfg.enabled:
        return None
    return AcmeHttp01Solver(cfg=http_cfg)
