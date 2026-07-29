"""
runtime/event_mesh.py
=====================
Event mesh foundation + transport layer (P3 / C-16–C-17 seam).

Joins local EventBuses and optionally forwards serialized Events through a
pluggable transport. ADR-008: Protocol + LocalEventMesh + null/file/http stubs.
ADR-009: durable SQLite broker + file/SQL peer discovery.
ADR-011: HTTP ingest listener + Docker Compose multi-node kit.
ADR-014: shared-secret auth for HTTP (+ actor mesh).

Service/lifecycle actor mesh (nng/socket) is ADR-012 (`runtime/actor_mesh.py`).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, runtime_checkable

from runtime.event_bus import Event, EventBus, Handler
from runtime.event_mesh_broker import (
    DurableEventBroker,
    DurableEventMeshTransport,
    FilePeerRegistry,
    MeshPeer,
)
from runtime.mesh_auth import MeshAuth, http_auth_headers, mesh_auth_from_config


@runtime_checkable
class EventMeshTransport(Protocol):
    def send(self, event: Event, *, origin_node: str) -> None:
        ...

    def close(self) -> None:
        ...


@dataclass
class NullEventMeshTransport:
    """Default transport: no cross-process delivery."""

    sent: list[Event] = field(default_factory=list)

    def send(self, event: Event, *, origin_node: str) -> None:
        self.sent.append(event)

    def close(self) -> None:
        return None


@dataclass
class FileEventMeshTransport:
    """Same-host stub: append JSONL envelopes under a directory.

    Not durable production messaging — useful for local dual-process experiments
    and tests. Readers call ``drain()`` / ``poll_ingest``.
    """

    directory: Path
    node_id: str = "local"

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        return self.directory / f"{self.node_id}.jsonl"

    def send(self, event: Event, *, origin_node: str) -> None:
        envelope = {
            "origin_node": origin_node,
            "event": event.to_dict(),
            "written_at": time.time(),
        }
        with self._path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope, sort_keys=True) + "\n")

    def drain(self, *, peer_glob: str = "*.jsonl") -> list[tuple[str, Event]]:
        """Read and clear peer JSONL files (except this node's own file)."""
        out: list[tuple[str, Event]] = []
        for path in sorted(self.directory.glob(peer_glob)):
            if path.name == f"{self.node_id}.jsonl":
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            path.write_text("", encoding="utf-8")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    origin = str(data.get("origin_node") or "unknown")
                    event = Event.from_dict(data.get("event") or {})
                    if event.topic:
                        out.append((origin, event))
                except Exception:
                    continue
        return out

    def close(self) -> None:
        return None


@dataclass
class HttpEventMeshTransport:
    """HTTP transport: POST event JSON to configured peer ingest URLs.

    Receive path is ``EventMeshHttpServer`` (``/mesh/ingest``) — used by the
    Docker multi-node kit (ADR-011). Sends ``Authorization`` when ``auth``
    has a token (ADR-014). Failures are soft so chat never breaks.
    """

    peers: list[str] = field(default_factory=list)
    timeout_s: float = 2.0
    auth: MeshAuth = field(default_factory=MeshAuth)
    posted: list[dict[str, Any]] = field(default_factory=list)

    def send(self, event: Event, *, origin_node: str) -> None:
        body = {"origin_node": origin_node, "event": event.to_dict()}
        self.posted.append(body)
        if not self.peers:
            return
        try:
            self.auth.ensure_ready(what="event mesh HTTP send")
        except Exception:
            return
        try:
            import requests
        except Exception:
            return
        headers = {"Content-Type": "application/json", **http_auth_headers(self.auth)}
        for url in self.peers:
            try:
                requests.post(
                    url, json=body, timeout=self.timeout_s, headers=headers
                )
            except Exception:
                continue

    def close(self) -> None:
        return None


@dataclass
class LocalEventMesh:
    """Bridge N in-process EventBuses (+ optional outbound transport)."""

    node_id: str
    buses: list[EventBus] = field(default_factory=list)
    transport: EventMeshTransport | None = None
    discovery: FilePeerRegistry | None = None
    http_server: Any = None
    _seen: set[str] = field(default_factory=set)
    _handlers: dict[int, Handler] = field(default_factory=dict)
    _attached: bool = False
    _forwarded: int = 0
    _ingested: int = 0

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = f"node-{uuid.uuid4().hex[:8]}"
        if self.transport is None:
            self.transport = NullEventMeshTransport()

    def attach(self) -> None:
        if self._attached:
            return
        for bus in self.buses:
            handler = self._make_forwarder(bus)
            self._handlers[id(bus)] = handler
            bus.subscribe("*", handler)
        self._attached = True
        self.heartbeat()

    def detach(self) -> None:
        for bus in self.buses:
            handler = self._handlers.pop(id(bus), None)
            if handler is not None:
                try:
                    bus.unsubscribe("*", handler)
                except Exception:
                    pass
        self._attached = False
        if self.http_server is not None:
            try:
                self.http_server.stop()
            except Exception:
                pass
            self.http_server = None
        if self.discovery is not None:
            try:
                self.discovery.close()
            except Exception:
                pass
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass

    def heartbeat(self, meta: Optional[dict[str, Any]] = None) -> None:
        """Refresh peer membership (file registry and/or durable broker)."""
        info = dict(meta or {})
        info.setdefault("node_id", self.node_id)
        if self.discovery is not None:
            try:
                self.discovery.announce(info)
            except Exception:
                pass
        transport = self.transport
        if isinstance(transport, DurableEventMeshTransport):
            try:
                transport.heartbeat(info)
            except Exception:
                pass

    def peers(self) -> list[MeshPeer]:
        transport = self.transport
        if isinstance(transport, DurableEventMeshTransport):
            try:
                return transport.peers()
            except Exception:
                pass
        if self.discovery is not None:
            return self.discovery.peers()
        return []

    def _make_forwarder(self, origin_bus: EventBus) -> Handler:
        def _forward(event: Event) -> None:
            self._fanout(event, origin_bus=origin_bus, outbound=True)

        return _forward

    def _fanout(
        self,
        event: Event,
        *,
        origin_bus: EventBus | None,
        outbound: bool,
    ) -> None:
        if not event.id or event.id in self._seen:
            return
        self._seen.add(event.id)
        if len(self._seen) > 5000:
            self._seen = set(list(self._seen)[-2500:])

        for bus in self.buses:
            if origin_bus is not None and bus is origin_bus:
                continue
            try:
                # Temporarily detach this bus's mesh forwarder to avoid loops.
                forwarder = self._handlers.get(id(bus))
                if forwarder is not None:
                    bus.unsubscribe("*", forwarder)
                try:
                    bus.emit(event)
                finally:
                    if forwarder is not None:
                        bus.subscribe("*", forwarder)
            except Exception:
                continue

        if outbound and self.transport is not None:
            try:
                self.transport.send(event, origin_node=self.node_id)
                self._forwarded += 1
            except Exception:
                pass

    def publish_local(
        self,
        topic: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "",
    ) -> Event:
        if not self.buses:
            event = Event(topic=topic, payload=payload or {}, source=source)
            if self.transport is not None:
                self.transport.send(event, origin_node=self.node_id)
            return event
        # Publish on the first bus; forwarder fans out to peers + transport.
        return self.buses[0].publish(topic, payload, source=source or self.node_id)

    def ingest(self, event: Event, *, from_node: str = "") -> None:
        """Accept a remote event onto all local buses (no outbound re-send)."""
        _ = from_node
        self._ingested += 1
        self._fanout(event, origin_bus=None, outbound=False)

    def poll_file_transport(self) -> int:
        """Drain FileEventMeshTransport peers into local buses. Returns count."""
        transport = self.transport
        if not isinstance(transport, FileEventMeshTransport):
            return 0
        count = 0
        for origin, event in transport.drain():
            self.ingest(event, from_node=origin)
            count += 1
        return count

    def poll_durable_transport(self, *, limit: int = 100) -> int:
        """Drain + ack DurableEventMeshTransport pending events. Returns count."""
        transport = self.transport
        if not isinstance(transport, DurableEventMeshTransport):
            return 0
        self.heartbeat()
        count = 0
        for origin, event in transport.drain(limit=limit):
            self.ingest(event, from_node=origin)
            try:
                transport.ack(event.id)
            except Exception:
                pass
            count += 1
        return count

    def poll(self, *, limit: int = 100) -> int:
        """Poll whichever transport supports inbound drain."""
        n = self.poll_durable_transport(limit=limit)
        if n:
            return n
        return self.poll_file_transport()

    def stats(self) -> dict[str, Any]:
        pending = None
        transport = self.transport
        if isinstance(transport, DurableEventMeshTransport):
            try:
                pending = transport.broker.pending_count()
            except Exception:
                pending = None
        return {
            "node_id": self.node_id,
            "attached": self._attached,
            "buses": len(self.buses),
            "forwarded": self._forwarded,
            "ingested": self._ingested,
            "seen": len(self._seen),
            "peers": len(self.peers()),
            "pending": pending,
            "transport": type(self.transport).__name__ if self.transport else None,
            "discovery": type(self.discovery).__name__ if self.discovery else None,
            "http_listen": (
                f"{self.http_server.host}:{self.http_server.port}"
                if self.http_server is not None
                else None
            ),
        }


def _resolve_under(root: Path, value: Any, default: Path) -> Path:
    path = Path(value) if value else default
    if not path.is_absolute():
        path = root / path
    return path


def _parse_http_peers(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def build_event_mesh(
    bus: EventBus,
    *,
    cfg: Optional[dict[str, Any]] = None,
    base: Path | None = None,
) -> LocalEventMesh | None:
    """Factory from config. Returns None when mesh is disabled."""
    data = dict(cfg or {})
    enabled = data.get("enabled", False)
    if isinstance(enabled, str):
        enabled = enabled.lower() in ("1", "true", "yes")
    env = os.environ.get("KERROS_EVENT_MESH")
    if env is not None:
        enabled = env.lower() in ("1", "true", "yes")
    if not enabled:
        return None

    root = Path(base or Path.home() / "offline_ai")
    node_id = (
        os.environ.get("KERROS_NODE_ID")
        or str(data.get("node_id") or "local")
    ).strip() or "local"
    transport_name = (
        os.environ.get("KERROS_EVENT_MESH_TRANSPORT")
        or str(data.get("transport") or "null")
    ).strip().lower()
    ttl_s = float(data.get("discovery_ttl_s") or 60)

    discovery_raw = data.get("discovery", None)
    if discovery_raw is None:
        discovery_mode = "auto" if transport_name == "durable" else "none"
    else:
        discovery_mode = str(discovery_raw).strip().lower() or "none"

    discovery: FilePeerRegistry | None = None
    if discovery_mode in ("file", "1", "true", "yes", "auto"):
        # "auto" only creates a file registry when durable (or explicit file).
        if discovery_mode != "auto" or transport_name == "durable":
            discovery_dir = _resolve_under(
                root,
                data.get("discovery_dir"),
                root / "data" / "event_mesh" / "peers",
            )
            discovery = FilePeerRegistry(
                directory=discovery_dir, node_id=node_id, ttl_s=ttl_s
            )

    mesh_auth = mesh_auth_from_config(data)

    transport: EventMeshTransport
    if transport_name == "file":
        directory = _resolve_under(
            root,
            data.get("file_dir"),
            root / "data" / "event_mesh",
        )
        transport = FileEventMeshTransport(directory=directory, node_id=node_id)
    elif transport_name == "http":
        peers = _parse_http_peers(
            os.environ.get("KERROS_EVENT_MESH_HTTP_PEERS")
            if os.environ.get("KERROS_EVENT_MESH_HTTP_PEERS") is not None
            else data.get("http_peers")
        )
        timeout_s = float(
            os.environ.get("KERROS_EVENT_MESH_HTTP_TIMEOUT")
            or data.get("http_timeout_s")
            or 2.0
        )
        transport = HttpEventMeshTransport(
            peers=peers, timeout_s=timeout_s, auth=mesh_auth
        )
    elif transport_name == "durable":
        broker_db = _resolve_under(
            root,
            data.get("broker_db"),
            root / "data" / "event_mesh" / "broker.db",
        )
        broker = DurableEventBroker(
            db_path=broker_db, node_id=node_id, peer_ttl_s=ttl_s
        )
        transport = DurableEventMeshTransport(
            broker=broker, discovery=discovery
        )
    else:
        transport = NullEventMeshTransport()

    mesh = LocalEventMesh(
        node_id=node_id,
        buses=[bus],
        transport=transport,
        discovery=discovery,
    )
    mesh.attach()

    # HTTP listen (Docker / multi-node receive). Opt-in via config or env.
    listen = (
        os.environ.get("KERROS_EVENT_MESH_LISTEN")
        if os.environ.get("KERROS_EVENT_MESH_LISTEN") is not None
        else data.get("http_listen")
    )
    if listen not in (None, "", False, "0", "false", "no", "off"):
        try:
            from runtime.event_mesh_http import start_mesh_http_server

            mesh.http_server = start_mesh_http_server(
                mesh, listen=listen, auth=mesh_auth
            )
        except Exception:
            pass

    return mesh
