"""
runtime/actor_mesh.py
=====================
IPC actor-mesh foundation (C-16 / ADR-012).

Bridges the in-process ServiceBus across processes/hosts via:

* ``socket`` — stdlib TCP framed JSON (always available; CI-friendly)
* ``nng`` — pynng Bus0 when installed (optional dependency)

Not a full orchestrator — request/reply helpers + topic fanout with loop
prevention. EventBus Docker/HTTP mesh remains ADR-008/011; this targets
service/lifecycle actor traffic (ADR-005 follow-on).
"""

from __future__ import annotations

import json
import os
import queue
import socket
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from runtime.mesh_auth import (
    MeshAuth,
    mesh_auth_from_config,
    unwrap_actor_payload,
    wrap_actor_payload,
)
from runtime.service_bus import ServiceBus


@dataclass
class ActorMessage:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    origin_node: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "pub"  # pub | req | rep
    reply_to: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "origin_node": self.origin_node,
            "kind": self.kind,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActorMessage":
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            topic=str(data.get("topic") or ""),
            payload=dict(data.get("payload") or {}),
            origin_node=str(data.get("origin_node") or ""),
            kind=str(data.get("kind") or "pub"),
            reply_to=str(data.get("reply_to") or ""),
            timestamp=float(data.get("timestamp") or time.time()),
        )

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "ActorMessage":
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("actor message must be a JSON object")
        return cls.from_dict(data)


def parse_tcp_url(url: str) -> tuple[str, int]:
    """Parse ``tcp://host:port`` or ``host:port`` into (host, port)."""
    text = str(url or "").strip()
    if text.startswith("tcp://"):
        text = text[len("tcp://") :]
    if text.startswith("ipc://") or text.startswith("inproc://"):
        raise ValueError(f"socket backend requires tcp:// URL, got {url!r}")
    if "://" in text:
        raise ValueError(f"unsupported URL scheme: {url!r}")
    host, _, port_s = text.rpartition(":")
    if not host or not port_s.isdigit():
        raise ValueError(f"invalid tcp address: {url!r}")
    return host, int(port_s)


def format_tcp_url(host: str, port: int) -> str:
    return f"tcp://{host}:{port}"


@runtime_checkable
class ActorMeshBackend(Protocol):
    def start(self) -> None:
        ...

    def send(self, data: bytes) -> None:
        ...

    def recv(self, timeout_s: float | None = None) -> bytes | None:
        ...

    def close(self) -> None:
        ...

    def endpoints(self) -> dict[str, Any]:
        ...


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf.extend(chunk)
    return bytes(buf)


def _send_frame(conn: socket.socket, data: bytes) -> None:
    conn.sendall(struct.pack("!I", len(data)) + data)


def _recv_frame(conn: socket.socket) -> bytes:
    header = _recv_exact(conn, 4)
    (length,) = struct.unpack("!I", header)
    if length > 8 * 1024 * 1024:
        raise ValueError(f"frame too large: {length}")
    return _recv_exact(conn, length)


@dataclass
class SocketActorBackend:
    """TCP framed-JSON pair/bus stub (stdlib only)."""

    listen: str | None = None
    peers: list[str] = field(default_factory=list)
    _sock: socket.socket | None = field(default=None, init=False, repr=False)
    _conns: list[socket.socket] = field(default_factory=list, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _inbox: queue.Queue = field(default_factory=queue.Queue, init=False, repr=False)
    _threads: list[threading.Thread] = field(default_factory=list, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _listen_host: str = field(default="", init=False)
    _listen_port: int = field(default=0, init=False)

    def start(self) -> None:
        self._stop.clear()
        if self.listen:
            host, port = parse_tcp_url(self.listen)
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((host, port))
            self._sock.listen(8)
            self._listen_host, self._listen_port = self._sock.getsockname()[:2]
            t = threading.Thread(target=self._accept_loop, name="actor-mesh-accept", daemon=True)
            t.start()
            self._threads.append(t)
        for peer in self.peers:
            self._dial(peer)

    def _accept_loop(self) -> None:
        assert self._sock is not None
        self._sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._add_conn(conn)

    def _dial(self, peer: str) -> None:
        host, port = parse_tcp_url(peer)
        last_exc: Exception | None = None
        for _ in range(50):
            if self._stop.is_set():
                return
            try:
                conn = socket.create_connection((host, port), timeout=1.0)
                self._add_conn(conn)
                return
            except OSError as exc:
                last_exc = exc
                time.sleep(0.05)
        if last_exc is not None:
            raise ConnectionError(f"failed to dial {peer}: {last_exc}") from last_exc

    def _add_conn(self, conn: socket.socket) -> None:
        conn.settimeout(0.5)
        with self._lock:
            self._conns.append(conn)
        t = threading.Thread(
            target=self._reader_loop,
            args=(conn,),
            name="actor-mesh-reader",
            daemon=True,
        )
        t.start()
        self._threads.append(t)

    def _reader_loop(self, conn: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                data = _recv_frame(conn)
            except socket.timeout:
                continue
            except Exception:
                break
            self._inbox.put(data)
        with self._lock:
            if conn in self._conns:
                self._conns.remove(conn)
        try:
            conn.close()
        except Exception:
            pass

    def send(self, data: bytes) -> None:
        dead: list[socket.socket] = []
        with self._lock:
            conns = list(self._conns)
        for conn in conns:
            try:
                _send_frame(conn, data)
            except Exception:
                dead.append(conn)
        if dead:
            with self._lock:
                for conn in dead:
                    if conn in self._conns:
                        self._conns.remove(conn)
                    try:
                        conn.close()
                    except Exception:
                        pass

    def recv(self, timeout_s: float | None = None) -> bytes | None:
        try:
            return self._inbox.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        with self._lock:
            conns = list(self._conns)
            self._conns.clear()
        for conn in conns:
            try:
                conn.close()
            except Exception:
                pass

    def endpoints(self) -> dict[str, Any]:
        listen = None
        if self._listen_port:
            listen = format_tcp_url(self._listen_host or "127.0.0.1", self._listen_port)
        elif self.listen:
            listen = self.listen
        return {"backend": "socket", "listen": listen, "peers": list(self.peers)}


@dataclass
class NngActorBackend:
    """pynng Bus0 backend (optional). Falls back unavailable without pynng."""

    listen: str | None = None
    peers: list[str] = field(default_factory=list)
    recv_timeout_ms: int = 100
    _sock: Any = field(default=None, init=False, repr=False)

    def start(self) -> None:
        try:
            import pynng
        except ImportError as exc:
            raise RuntimeError(
                "nng backend requires pynng — pip install pynng"
            ) from exc
        sock = pynng.Bus0()
        # Non-blocking-ish recv via timeout.
        sock.recv_timeout = self.recv_timeout_ms
        sock.send_timeout = 1000
        if self.listen:
            sock.listen(self.listen)
        for peer in self.peers:
            sock.dial(peer)
        self._sock = sock
        # Bus topology needs a short settle time after dial/listen.
        time.sleep(0.05)

    def send(self, data: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("nng backend not started")
        self._sock.send(data)

    def recv(self, timeout_s: float | None = None) -> bytes | None:
        if self._sock is None:
            raise RuntimeError("nng backend not started")
        if timeout_s is not None:
            self._sock.recv_timeout = max(1, int(timeout_s * 1000))
        try:
            return self._sock.recv()
        except Exception:
            return None

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def endpoints(self) -> dict[str, Any]:
        return {"backend": "nng", "listen": self.listen, "peers": list(self.peers)}


def nng_available() -> bool:
    try:
        import pynng  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class ActorMesh:
    """Bridge local ServiceBus traffic across an ActorMeshBackend.

    Use ``ActorMesh.publish`` (not raw ``ServiceBus.publish``) so messages
    fan out to remote peers. Inbound remote messages are re-published on the
    local ServiceBus. When ``auth`` has a token, wire envelopes carry it
    (ADR-014).
    """

    node_id: str
    bus: ServiceBus
    backend: ActorMeshBackend
    auth: MeshAuth = field(default_factory=MeshAuth)
    _seen: set[str] = field(default_factory=set)
    _attached: bool = False
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _forwarded: int = 0
    _ingested: int = 0
    _auth_rejected: int = 0

    def attach(self) -> None:
        if self._attached:
            return
        self.auth.ensure_ready(what="actor mesh")
        self.backend.start()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._recv_loop, name=f"actor-mesh-{self.node_id}", daemon=True
        )
        self._thread.start()
        self._attached = True

    def detach(self) -> None:
        self._stop.set()
        self._attached = False
        try:
            self.backend.close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _mark_seen(self, msg_id: str) -> bool:
        if not msg_id or msg_id in self._seen:
            return False
        self._seen.add(msg_id)
        if len(self._seen) > 5000:
            self._seen = set(list(self._seen)[-2500:])
        return True

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> ActorMessage:
        msg = ActorMessage(
            topic=topic,
            payload=dict(payload or {}),
            origin_node=self.node_id,
            kind="pub",
        )
        self._mark_seen(msg.id)
        self._deliver_local(msg)
        try:
            self.backend.send(self._encode(msg))
            self._forwarded += 1
        except Exception:
            pass
        return msg

    def _encode(self, msg: ActorMessage) -> bytes:
        envelope = wrap_actor_payload(msg.to_dict(), self.auth)
        return json.dumps(envelope, sort_keys=True).encode("utf-8")

    def _decode(self, raw: bytes) -> ActorMessage:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("actor message must be a JSON object")
        inner = unwrap_actor_payload(data, self.auth)
        return ActorMessage.from_dict(inner)

    def _deliver_local(self, msg: ActorMessage) -> None:
        if not msg.topic:
            return
        try:
            self.bus.publish(msg.topic, dict(msg.payload))
        except Exception:
            pass

    def _recv_loop(self) -> None:
        while not self._stop.is_set():
            try:
                raw = self.backend.recv(timeout_s=0.2)
            except Exception:
                continue
            if not raw:
                continue
            try:
                msg = self._decode(raw)
            except PermissionError:
                self._auth_rejected += 1
                continue
            except Exception:
                continue
            if msg.origin_node == self.node_id:
                continue
            if not self._mark_seen(msg.id):
                continue
            self._ingested += 1
            self._deliver_local(msg)

    def stats(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "attached": self._attached,
            "forwarded": self._forwarded,
            "ingested": self._ingested,
            "auth_rejected": self._auth_rejected,
            "auth": self.auth.enabled,
            "seen": len(self._seen),
            "endpoints": self.backend.endpoints(),
        }


def build_actor_backend(
    *,
    backend: str,
    listen: str | None,
    peers: list[str],
) -> ActorMeshBackend:
    name = (backend or "socket").strip().lower()
    if name == "nng":
        return NngActorBackend(listen=listen, peers=peers)
    if name in ("socket", "tcp"):
        return SocketActorBackend(listen=listen, peers=peers)
    raise ValueError(f"unknown actor mesh backend: {backend!r}")


def build_actor_mesh(
    bus: ServiceBus,
    *,
    cfg: Optional[dict[str, Any]] = None,
) -> ActorMesh | None:
    """Factory from config/env. Returns None when disabled."""
    data = dict(cfg or {})
    enabled = data.get("enabled", False)
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("1", "true", "yes")
    env = os.environ.get("KERROS_ACTOR_MESH")
    if env is not None:
        enabled = env.lower() in ("1", "true", "yes")
    if not enabled:
        return None

    node_id = (
        os.environ.get("KERROS_NODE_ID")
        or str(data.get("node_id") or "local")
    ).strip() or "local"
    backend_name = (
        os.environ.get("KERROS_ACTOR_MESH_BACKEND")
        or str(data.get("backend") or "socket")
    ).strip().lower()
    listen = os.environ.get("KERROS_ACTOR_MESH_LISTEN")
    if listen is None:
        listen = data.get("listen")
    peers_raw = os.environ.get("KERROS_ACTOR_MESH_PEERS")
    if peers_raw is not None:
        peers = [p.strip() for p in peers_raw.split(",") if p.strip()]
    else:
        peers = [str(p).strip() for p in (data.get("peers") or []) if str(p).strip()]

    if backend_name == "nng" and not nng_available():
        # Soft fallback so boot never fails on Termux without pynng.
        backend_name = "socket"

    auth = mesh_auth_from_config(
        data,
        env_token="KERROS_ACTOR_MESH_TOKEN",
        env_required="KERROS_ACTOR_MESH_AUTH_REQUIRED",
    )

    backend = build_actor_backend(
        backend=backend_name, listen=listen or None, peers=peers
    )
    mesh = ActorMesh(node_id=node_id, bus=bus, backend=backend, auth=auth)
    mesh.attach()
    return mesh
