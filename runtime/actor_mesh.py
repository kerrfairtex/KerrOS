"""
runtime/actor_mesh.py
=====================
IPC actor-mesh foundation (C-16 / ADR-012) + orchestrator foundation (ADR-018).

Bridges the in-process ServiceBus across processes/hosts via:

* ``socket`` — stdlib TCP framed JSON (always available; CI-friendly)
* ``nng`` — pynng Bus0 when installed (optional dependency)
* ``nats`` — soft nats-py backend (ADR-023; falls back to socket if missing)

Orchestrator layer (still narrow): named actors, in-memory routes,
request/reply, and runtime peer dial for authenticated WAN (ADR-014 tokens).
ADR-023 adds optional in-process TLS/mTLS for the socket backend, soft NATS,
and opt-in ServiceManager restart hooks for dead actors.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import ssl
import struct
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from runtime.mesh_auth import (
    MeshAuth,
    mesh_auth_from_config,
    unwrap_actor_payload,
    wrap_actor_payload,
)
from runtime.service_bus import ServiceBus

ActorHandler = Callable[["ActorMessage"], dict[str, Any] | None]


@dataclass
class ActorMessage:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    origin_node: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "pub"  # pub | req | rep
    reply_to: str = ""
    actor: str = ""  # named actor for req/rep (ADR-018)
    target_node: str = ""  # empty = fanout; else only that node delivers
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "origin_node": self.origin_node,
            "kind": self.kind,
            "reply_to": self.reply_to,
            "actor": self.actor,
            "target_node": self.target_node,
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
            actor=str(data.get("actor") or ""),
            target_node=str(data.get("target_node") or ""),
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


def listen_is_loopback(listen: str | None) -> bool:
    """True when listen is unset or bound to loopback (dev-safe)."""
    if not listen:
        return True
    try:
        host, _port = parse_tcp_url(listen)
    except ValueError:
        return False
    return host in ("127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1")


def parse_routes(raw: Any) -> dict[str, str]:
    """Parse routes from dict or ``name=node,name2=node2`` string."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {
            str(k).strip(): str(v).strip()
            for k, v in raw.items()
            if str(k).strip() and str(v).strip()
        }
    text = str(raw).strip()
    if not text:
        return {}
    out: dict[str, str] = {}
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, node = part.partition("=")
        name, node = name.strip(), node.strip()
        if name and node:
            out[name] = node
    return out


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
    """TCP framed-JSON pair/bus stub (stdlib only).

    Optional ``ssl_server_context`` / ``ssl_client_context`` enable TLS/mTLS
    (ADR-023). Plain TCP when both are None.
    """

    listen: str | None = None
    peers: list[str] = field(default_factory=list)
    ssl_server_context: ssl.SSLContext | None = None
    ssl_client_context: ssl.SSLContext | None = None
    _sock: socket.socket | None = field(default=None, init=False, repr=False)
    _conns: list[socket.socket] = field(default_factory=list, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _inbox: queue.Queue = field(default_factory=queue.Queue, init=False, repr=False)
    _threads: list[threading.Thread] = field(default_factory=list, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _listen_host: str = field(default="", init=False)
    _listen_port: int = field(default=0, init=False)
    _started: bool = field(default=False, init=False)

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
        for peer in list(self.peers):
            self._dial(peer)
        self._started = True

    def dial(self, peer: str) -> None:
        """Dial a peer at runtime (WAN join / late binding)."""
        url = str(peer or "").strip()
        if not url:
            raise ValueError("empty peer URL")
        if url not in self.peers:
            self.peers.append(url)
        if self._started:
            self._dial(url)
        # If not started yet, start() will dial from peers list.

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
            if self.ssl_server_context is not None:
                try:
                    conn = self.ssl_server_context.wrap_socket(conn, server_side=True)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    continue
            self._add_conn(conn)

    def _dial(self, peer: str) -> None:
        host, port = parse_tcp_url(peer)
        last_exc: Exception | None = None
        for _ in range(50):
            if self._stop.is_set():
                return
            try:
                conn = socket.create_connection((host, port), timeout=1.0)
                if self.ssl_client_context is not None:
                    conn = self.ssl_client_context.wrap_socket(
                        conn, server_hostname=host if self.ssl_client_context.check_hostname else None
                    )
                self._add_conn(conn)
                return
            except OSError as exc:
                last_exc = exc
                time.sleep(0.05)
            except ssl.SSLError as exc:
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
        self._started = False
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
        return {
            "backend": "socket",
            "listen": listen,
            "peers": list(self.peers),
            "tls": self.ssl_server_context is not None or self.ssl_client_context is not None,
        }


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

    def dial(self, peer: str) -> None:
        url = str(peer or "").strip()
        if not url:
            raise ValueError("empty peer URL")
        if url not in self.peers:
            self.peers.append(url)
        if self._sock is None:
            return
        self._sock.dial(url)
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

    ADR-018 adds named actors, routes, request/reply, and ``add_peer``.
    ADR-020 adds optional local supervision (``supervisor``).
    ADR-028 adds optional JetStream soft client, OTP tree, CA reload holder.
    """

    node_id: str
    bus: ServiceBus
    backend: ActorMeshBackend
    auth: MeshAuth = field(default_factory=MeshAuth)
    routes: dict[str, str] = field(default_factory=dict)
    supervisor: Any = None  # optional ActorSupervisor (ADR-020)
    jetstream: Any = None  # optional JetStreamSoftClient (ADR-028)
    supervision_tree: Any = None  # optional SupervisionTree (ADR-028)
    tls_holder: Any = None  # optional ReloadingTlsHolder (ADR-028)
    _handlers: dict[str, ActorHandler] = field(default_factory=dict, init=False, repr=False)
    _pending: dict[str, tuple[threading.Event, dict[str, Any]]] = field(
        default_factory=dict, init=False, repr=False
    )
    _pending_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _seen: set[str] = field(default_factory=set)
    _attached: bool = False
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _forwarded: int = 0
    _ingested: int = 0
    _auth_rejected: int = 0
    _requests: int = 0
    _replies: int = 0

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
        if self.supervisor is not None:
            # Auto ping actor for remote liveness probes (ADR-020).
            cfg = getattr(self.supervisor, "config", None)
            if cfg is not None and getattr(cfg, "auto_register_ping", False):
                if "_sys.ping" not in self._handlers:
                    self.register("_sys.ping", self._sys_ping_handler)
            try:
                self.supervisor.attach()
            except Exception:
                pass

    def detach(self) -> None:
        if self.supervisor is not None:
            try:
                self.supervisor.detach()
            except Exception:
                pass
        self._stop.set()
        self._attached = False
        try:
            self.backend.close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._pending_lock:
            for event, box in self._pending.values():
                box["error"] = "mesh detached"
                event.set()
            self._pending.clear()

    def _sys_ping_handler(self, msg: ActorMessage) -> dict[str, Any]:
        return {
            "ok": True,
            "node_id": self.node_id,
            "handlers": sorted(self._handlers),
            "ts": time.time(),
        }

    def register(self, name: str, handler: ActorHandler) -> None:
        key = str(name or "").strip()
        if not key:
            raise ValueError("actor name required")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[key] = handler
        if self.supervisor is not None:
            try:
                self.supervisor.observe(key, node_id=self.node_id)
            except Exception:
                pass

    def unregister(self, name: str) -> None:
        key = str(name or "").strip()
        self._handlers.pop(key, None)
        if self.supervisor is not None:
            try:
                self.supervisor.forget(key)
            except Exception:
                pass

    def set_route(self, name: str, node_id: str) -> None:
        key = str(name or "").strip()
        node = str(node_id or "").strip()
        if not key or not node:
            raise ValueError("actor name and node_id required")
        self.routes[key] = node

    def add_peer(self, url: str) -> None:
        """Dial a peer after attach (WAN join)."""
        dial = getattr(self.backend, "dial", None)
        if not callable(dial):
            raise RuntimeError(
                f"backend {type(self.backend).__name__} does not support dial"
            )
        dial(url)

    def _mark_seen(self, msg_id: str) -> bool:
        if not msg_id or msg_id in self._seen:
            return False
        self._seen.add(msg_id)
        if len(self._seen) > 5000:
            self._seen = set(list(self._seen)[-2500:])
        return True

    def publish(
        self,
        topic: str,
        payload: dict[str, Any] | None = None,
        *,
        target_node: str = "",
    ) -> ActorMessage:
        msg = ActorMessage(
            topic=topic,
            payload=dict(payload or {}),
            origin_node=self.node_id,
            kind="pub",
            target_node=str(target_node or ""),
        )
        self._mark_seen(msg.id)
        if not msg.target_node or msg.target_node == self.node_id:
            self._deliver_local(msg)
        try:
            self.backend.send(self._encode(msg))
            self._forwarded += 1
        except Exception:
            pass
        return msg

    def request(
        self,
        actor: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_s: float = 5.0,
    ) -> dict[str, Any]:
        """RPC-style request to a named actor (local handler or routed node)."""
        name = str(actor or "").strip()
        if not name:
            raise ValueError("actor name required")

        # Local-only: no route or route points at self.
        target = str(self.routes.get(name) or "").strip()
        if (not target or target == self.node_id) and name in self._handlers:
            result = self._handlers[name](
                ActorMessage(
                    topic=f"actor.{name}",
                    actor=name,
                    payload=dict(payload or {}),
                    origin_node=self.node_id,
                    kind="req",
                    target_node=self.node_id,
                )
            )
            return dict(result or {})

        if not target:
            raise KeyError(f"no route for actor {name!r}")

        msg = ActorMessage(
            topic=f"actor.{name}",
            actor=name,
            payload=dict(payload or {}),
            origin_node=self.node_id,
            kind="req",
            target_node=target,
        )
        event = threading.Event()
        box: dict[str, Any] = {}
        with self._pending_lock:
            self._pending[msg.id] = (event, box)
        self._mark_seen(msg.id)
        try:
            self.backend.send(self._encode(msg))
            self._forwarded += 1
            self._requests += 1
        except Exception as exc:
            with self._pending_lock:
                self._pending.pop(msg.id, None)
            raise ConnectionError(f"failed to send request to {name!r}: {exc}") from exc

        if not event.wait(timeout=max(0.01, float(timeout_s))):
            with self._pending_lock:
                self._pending.pop(msg.id, None)
            raise TimeoutError(
                f"actor request {name!r} timed out after {timeout_s}s "
                f"(target_node={target})"
            )
        if box.get("error"):
            raise RuntimeError(str(box["error"]))
        return dict(box.get("payload") or {})

    def reply(self, req: ActorMessage, payload: dict[str, Any] | None = None) -> ActorMessage:
        """Send a ``rep`` for an inbound ``req`` (usually called by the mesh)."""
        msg = ActorMessage(
            topic=req.topic,
            actor=req.actor,
            payload=dict(payload or {}),
            origin_node=self.node_id,
            kind="rep",
            reply_to=req.id,
            target_node=req.origin_node,
        )
        self._mark_seen(msg.id)
        try:
            self.backend.send(self._encode(msg))
            self._forwarded += 1
            self._replies += 1
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

    def _complete_pending(self, msg: ActorMessage) -> None:
        key = msg.reply_to
        if not key:
            return
        with self._pending_lock:
            item = self._pending.pop(key, None)
        if not item:
            return
        event, box = item
        box["payload"] = dict(msg.payload or {})
        event.set()

    def _handle_request(self, msg: ActorMessage) -> None:
        name = (msg.actor or "").strip()
        if not name and msg.topic.startswith("actor."):
            name = msg.topic[len("actor.") :]
        handler = self._handlers.get(name) if name else None
        if handler is None:
            self.reply(msg, {"ok": False, "error": f"no handler for actor {name!r}"})
            return
        try:
            result = handler(msg)
            self.reply(msg, dict(result or {}))
        except Exception as exc:
            self.reply(msg, {"ok": False, "error": str(exc)})

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
            # Targeted delivery: ignore messages for other nodes.
            if msg.target_node and msg.target_node != self.node_id:
                continue
            self._ingested += 1
            if msg.kind == "rep":
                self._complete_pending(msg)
                continue
            if msg.kind == "req":
                self._handle_request(msg)
                continue
            self._deliver_local(msg)

    def stats(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "attached": self._attached,
            "forwarded": self._forwarded,
            "ingested": self._ingested,
            "auth_rejected": self._auth_rejected,
            "auth": self.auth.enabled,
            "requests": self._requests,
            "replies": self._replies,
            "handlers": sorted(self._handlers),
            "routes": dict(self.routes),
            "seen": len(self._seen),
            "endpoints": self.backend.endpoints(),
            "supervision": (
                self.supervisor.stats() if self.supervisor is not None else None
            ),
            "jetstream": (
                self.jetstream.stats() if self.jetstream is not None else None
            ),
            "supervision_tree": (
                self.supervision_tree.stats()
                if self.supervision_tree is not None
                else None
            ),
            "tls_reload": (
                self.tls_holder.stats() if self.tls_holder is not None else None
            ),
        }


def build_actor_backend(
    *,
    backend: str,
    listen: str | None,
    peers: list[str],
    ssl_server_context: ssl.SSLContext | None = None,
    ssl_client_context: ssl.SSLContext | None = None,
    nats_url: str = "",
    nats_subject_prefix: str = "kerros.actor",
    node_id: str = "local",
    nats_client: Any = None,
) -> ActorMeshBackend:
    name = (backend or "socket").strip().lower()
    if name == "nng":
        return NngActorBackend(listen=listen, peers=peers)
    if name == "nats":
        from runtime.nats_actor_backend import NatsActorBackend

        return NatsActorBackend(
            url=nats_url or "nats://127.0.0.1:4222",
            subject_prefix=nats_subject_prefix or "kerros.actor",
            node_id=node_id,
            listen=listen,
            peers=peers,
            client=nats_client,
        )
    if name in ("socket", "tcp"):
        return SocketActorBackend(
            listen=listen,
            peers=peers,
            ssl_server_context=ssl_server_context,
            ssl_client_context=ssl_client_context,
        )
    raise ValueError(f"unknown actor mesh backend: {backend!r}")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


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

    routes_env = os.environ.get("KERROS_ACTOR_MESH_ROUTES")
    routes = parse_routes(routes_env if routes_env is not None else data.get("routes"))

    if backend_name == "nng" and not nng_available():
        # Soft fallback so boot never fails on Termux without pynng.
        backend_name = "socket"
    if backend_name == "nats":
        from runtime.nats_actor_backend import nats_available

        if not nats_available() and data.get("_nats_client") is None:
            backend_name = "socket"

    auth = mesh_auth_from_config(
        data,
        env_token="KERROS_ACTOR_MESH_TOKEN",
        env_required="KERROS_ACTOR_MESH_AUTH_REQUIRED",
    )

    # WAN-safe default: non-loopback listen requires a token when flagged.
    non_loop_raw = os.environ.get("KERROS_ACTOR_MESH_AUTH_REQUIRED_NON_LOOPBACK")
    if non_loop_raw is None:
        non_loop_raw = data.get("auth_required_non_loopback", False)
    if _truthy(non_loop_raw) and not listen_is_loopback(listen or None):
        if not auth.token:
            raise RuntimeError(
                "actor mesh: non-loopback listen requires auth_token / "
                "KERROS_ACTOR_MESH_TOKEN when auth_required_non_loopback is set"
            )
        auth = MeshAuth(token=auth.token, required=True)

    ssl_server = None
    ssl_client = None
    tls_holder = None
    tls_raw = data.get("tls") or {}
    from runtime.actor_mesh_tls import (
        MeshTlsConfig,
        MeshTlsError,
        ReloadingTlsHolder,
        build_client_ssl_context,
        build_server_ssl_context,
    )

    tls_cfg = MeshTlsConfig.from_mapping(tls_raw, base=None)
    if tls_cfg.enabled:
        if backend_name not in ("socket", "tcp"):
            raise MeshTlsError("actor mesh TLS applies only to socket/tcp backend")
        try:
            if tls_cfg.reload:
                tls_holder = ReloadingTlsHolder.from_config(tls_cfg)
                ssl_server = tls_holder.server_context
                ssl_client = tls_holder.client_context
            else:
                ssl_server = build_server_ssl_context(tls_cfg)
                ssl_client = build_client_ssl_context(tls_cfg)
        except MeshTlsError:
            raise
        except Exception as exc:
            raise MeshTlsError(str(exc)) from exc

    nats_cfg = dict(data.get("nats") or {})
    nats_url = (
        os.environ.get("KERROS_ACTOR_MESH_NATS_URL")
        or str(nats_cfg.get("url") or "nats://127.0.0.1:4222")
    )
    nats_prefix = (
        os.environ.get("KERROS_ACTOR_MESH_NATS_PREFIX")
        or str(nats_cfg.get("subject_prefix") or "kerros.actor")
    )

    backend = build_actor_backend(
        backend=backend_name,
        listen=listen or None,
        peers=peers,
        ssl_server_context=ssl_server,
        ssl_client_context=ssl_client,
        nats_url=nats_url,
        nats_subject_prefix=nats_prefix,
        node_id=node_id,
        nats_client=data.get("_nats_client"),
    )
    mesh = ActorMesh(
        node_id=node_id,
        bus=bus,
        backend=backend,
        auth=auth,
        routes=routes,
        tls_holder=tls_holder,
    )

    from runtime.actor_supervision import ActorSupervisor, SupervisionConfig
    from runtime.actor_remote_supervision import (
        RemoteSupervisionConfig,
        build_remote_restart_hook,
    )
    from runtime.actor_supervision_tree import build_supervision_tree

    sup_raw = dict(data.get("supervision") or {})
    sup_cfg = SupervisionConfig.from_mapping(sup_raw)
    if sup_cfg.enabled:
        remote_cfg = RemoteSupervisionConfig.from_mapping(sup_raw)
        on_dead = build_remote_restart_hook(
            cfg=remote_cfg,
            manager=data.get("_service_manager"),
        )
        mesh.supervisor = ActorSupervisor(
            mesh=mesh, config=sup_cfg, on_dead=on_dead
        )
        tree_raw = dict(sup_raw.get("tree") or {})
        tree_enabled = tree_raw.get("enabled", False)
        env_t = os.environ.get("KERROS_ACTOR_MESH_SUPERVISION_TREE")
        if env_t is not None:
            tree_enabled = _truthy(env_t)
        else:
            tree_enabled = _truthy(tree_enabled)
        mesh.supervision_tree = build_supervision_tree(
            enabled=bool(tree_enabled),
            strategy=str(tree_raw.get("strategy") or "one_for_one"),
        )

    # ADR-028: optional JetStream soft client (injected or soft nats-py).
    js_raw = dict(nats_cfg.get("jetstream") or {})
    js_raw.setdefault("url", nats_url)
    js_raw.setdefault("subject_prefix", nats_prefix)
    from dataclasses import replace

    from runtime.nats_jetstream import JetStreamSoftClient, jetstream_config_from

    js_cfg = jetstream_config_from(js_raw)
    injected_js = data.get("_jetstream_client")
    if js_cfg.enabled or injected_js is not None:
        effective = js_cfg if js_cfg.enabled else replace(js_cfg, enabled=True)
        try:
            mesh.jetstream = JetStreamSoftClient(cfg=effective, client=injected_js)
            mesh.jetstream.start()
        except Exception:
            if injected_js is not None:
                raise
            mesh.jetstream = None

    mesh.attach()
    return mesh
