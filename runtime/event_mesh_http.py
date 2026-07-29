"""
runtime/event_mesh_http.py
==========================
HTTP ingest/listen for Docker / multi-node event mesh (C-17 / ADR-011 / ADR-014).

Stdlib ``ThreadingHTTPServer`` — no Flask/FastAPI dependency. Peers POST
``{"origin_node", "event"}`` to ``/mesh/ingest``; the handler calls
``LocalEventMesh.ingest`` (no outbound re-send).

When ``MeshAuth`` has a token, ``POST /mesh/ingest`` and ``POST /mesh/publish``
require ``Authorization: Bearer <token>`` or ``X-Kerros-Mesh-Token``.
``GET /health`` stays open for probes.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from runtime.mesh_auth import MeshAuth, check_http_auth

if TYPE_CHECKING:
    from runtime.event_mesh import LocalEventMesh


def parse_listen_addr(value: str | int | None, *, default_port: int = 8787) -> tuple[str, int]:
    """Parse ``host:port``, ``:port``, or bare port into (host, port)."""
    if value is None or value == "":
        return ("0.0.0.0", default_port)
    if isinstance(value, int):
        return ("0.0.0.0", int(value))
    text = str(value).strip()
    if text.isdigit():
        return ("0.0.0.0", int(text))
    if "://" in text:
        parsed = urlparse(text)
        host = parsed.hostname or "0.0.0.0"
        port = int(parsed.port or default_port)
        return (host, port)
    if text.startswith(":"):
        return ("0.0.0.0", int(text[1:]))
    if ":" in text:
        host, _, port_s = text.rpartition(":")
        return (host or "0.0.0.0", int(port_s))
    raise ValueError(f"invalid listen address: {value!r}")


@dataclass
class EventMeshHttpServer:
    """Background HTTP server bound to a LocalEventMesh."""

    mesh: "LocalEventMesh"
    host: str = "0.0.0.0"
    port: int = 8787
    auth: MeshAuth = field(default_factory=MeshAuth)
    path_ingest: str = "/mesh/ingest"
    path_publish: str = "/mesh/publish"
    path_health: str = "/health"
    _httpd: ThreadingHTTPServer | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    received: int = 0
    published: int = 0
    rejected_auth: int = 0

    def start(self) -> None:
        if self._httpd is not None:
            return
        self.auth.ensure_ready(what="event mesh HTTP listen")
        mesh = self.mesh
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except Exception as exc:
                    raise ValueError(f"invalid JSON: {exc}") from exc
                if not isinstance(data, dict):
                    raise ValueError("JSON body must be an object")
                return data

            def _write(self, code: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body, sort_keys=True).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _require_auth(self) -> bool:
                if check_http_auth(self.headers, server.auth):
                    return True
                server.rejected_auth += 1
                self._write(401, {"ok": False, "error": "unauthorized"})
                return False

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path == server.path_health:
                    stats = mesh.stats()
                    self._write(
                        200,
                        {
                            "ok": True,
                            "node_id": mesh.node_id,
                            "auth": server.auth.enabled,
                            "stats": stats,
                        },
                    )
                    return
                self._write(404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in (server.path_ingest, server.path_publish):
                    if not self._require_auth():
                        return
                try:
                    data = self._read_json()
                except ValueError as exc:
                    self._write(400, {"ok": False, "error": str(exc)})
                    return

                if path == server.path_ingest:
                    try:
                        from runtime.event_bus import Event

                        event_data = data.get("event") or {}
                        if not isinstance(event_data, dict):
                            raise ValueError("event must be an object")
                        event = Event.from_dict(event_data)
                        if not event.topic:
                            raise ValueError("event.topic required")
                        origin = str(data.get("origin_node") or "")
                        mesh.ingest(event, from_node=origin)
                        server.received += 1
                        self._write(
                            200,
                            {
                                "ok": True,
                                "ingested": True,
                                "event_id": event.id,
                                "node_id": mesh.node_id,
                            },
                        )
                    except Exception as exc:
                        self._write(400, {"ok": False, "error": str(exc)})
                    return

                if path == server.path_publish:
                    try:
                        topic = str(data.get("topic") or "").strip()
                        if not topic:
                            raise ValueError("topic required")
                        payload = data.get("payload")
                        if payload is None:
                            payload = {}
                        if not isinstance(payload, dict):
                            raise ValueError("payload must be an object")
                        source = str(data.get("source") or mesh.node_id)
                        event = mesh.publish_local(topic, payload, source=source)
                        server.published += 1
                        self._write(
                            200,
                            {
                                "ok": True,
                                "event_id": event.id,
                                "topic": event.topic,
                                "node_id": mesh.node_id,
                            },
                        )
                    except Exception as exc:
                        self._write(400, {"ok": False, "error": str(exc)})
                    return

                self._write(404, {"ok": False, "error": "not found"})

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        # Allow tests to bind ephemeral port 0 then read actual port.
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name=f"event-mesh-http-{mesh.node_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is None:
            return
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
    def url_ingest(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}{self.path_ingest}"

    @property
    def url_health(self) -> str:
        host = "127.0.0.1" if self.host in ("0.0.0.0", "::") else self.host
        return f"http://{host}:{self.port}{self.path_health}"


def start_mesh_http_server(
    mesh: "LocalEventMesh",
    *,
    listen: str | int | None = None,
    host: str | None = None,
    port: int | None = None,
    auth: MeshAuth | None = None,
) -> EventMeshHttpServer:
    """Create and start an EventMeshHttpServer attached to ``mesh``."""
    if host is None or port is None:
        h, p = parse_listen_addr(listen)
        host = host or h
        port = port if port is not None else p
    server = EventMeshHttpServer(
        mesh=mesh,
        host=str(host),
        port=int(port),
        auth=auth or MeshAuth(),
    )
    server.start()
    return server
