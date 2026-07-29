"""
runtime/event_mesh.py
=====================
Event mesh foundation (P3 / C-16 seam).

Joins local EventBuses and optionally forwards serialized Events through a
pluggable transport. Full multi-node discovery, durable brokers, and nng/socket
actor meshes remain deferred — this ships the Protocol + LocalEventMesh so
later transports plug in without changing EventBus callers.
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
    """Stub HTTP transport: POST event JSON to configured peer URLs.

    Receive path is intentionally out of scope (use LocalEventMesh.ingest in
    tests / future webhook). Failures are soft so chat never breaks.
    """

    peers: list[str] = field(default_factory=list)
    timeout_s: float = 2.0
    posted: list[dict[str, Any]] = field(default_factory=list)

    def send(self, event: Event, *, origin_node: str) -> None:
        body = {"origin_node": origin_node, "event": event.to_dict()}
        self.posted.append(body)
        if not self.peers:
            return
        try:
            import requests
        except Exception:
            return
        for url in self.peers:
            try:
                requests.post(url, json=body, timeout=self.timeout_s)
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

    def detach(self) -> None:
        for bus in self.buses:
            handler = self._handlers.pop(id(bus), None)
            if handler is not None:
                try:
                    bus.unsubscribe("*", handler)
                except Exception:
                    pass
        self._attached = False
        if self.transport is not None:
            try:
                self.transport.close()
            except Exception:
                pass

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

    def stats(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "attached": self._attached,
            "buses": len(self.buses),
            "forwarded": self._forwarded,
            "ingested": self._ingested,
            "seen": len(self._seen),
            "transport": type(self.transport).__name__ if self.transport else None,
        }


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

    node_id = (
        os.environ.get("KERROS_NODE_ID")
        or str(data.get("node_id") or "local")
    ).strip() or "local"
    transport_name = str(data.get("transport") or "null").strip().lower()
    transport: EventMeshTransport
    if transport_name == "file":
        root = Path(base or Path.home() / "offline_ai")
        directory = Path(
            data.get("file_dir") or (root / "data" / "event_mesh")
        )
        if not directory.is_absolute():
            directory = root / directory
        transport = FileEventMeshTransport(directory=directory, node_id=node_id)
    elif transport_name == "http":
        peers = list(data.get("http_peers") or [])
        transport = HttpEventMeshTransport(peers=peers)
    else:
        transport = NullEventMeshTransport()

    mesh = LocalEventMesh(node_id=node_id, buses=[bus], transport=transport)
    mesh.attach()
    return mesh
