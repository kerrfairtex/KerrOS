"""
runtime/event_mesh_broker.py
============================
Event mesh transport layer (P3 / C-16): peer discovery + durable broker.

Builds on ADR-008's EventMeshTransport seam. Same-host / shared-filesystem
multi-process mesh without requiring NATS/Redis/nng. Docker multi-node and
nng actor IPC remain deferred (C-17 / C-16 full).
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from runtime.event_bus import Event


SCHEMA = """
CREATE TABLE IF NOT EXISTS mesh_messages (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    origin_node TEXT NOT NULL,
    event_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mesh_msg_created ON mesh_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_mesh_msg_origin ON mesh_messages(origin_node);

CREATE TABLE IF NOT EXISTS mesh_acks (
    event_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    acked_at REAL NOT NULL,
    PRIMARY KEY (event_id, node_id)
);

CREATE TABLE IF NOT EXISTS mesh_peers (
    node_id TEXT PRIMARY KEY,
    last_seen REAL NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, sort_keys=True)


def _loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


@dataclass(frozen=True)
class MeshPeer:
    node_id: str
    last_seen: float
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.last_seen)


@dataclass
class FilePeerRegistry:
    """Shared-directory membership: each node writes ``<node_id>.json`` heartbeats.

    Useful when processes share a filesystem but do not share the SQLite broker
    peer table (or as a lightweight discovery sidecar).
    """

    directory: Path
    node_id: str
    ttl_s: float = 60.0

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, node_id: str | None = None) -> Path:
        return self.directory / f"{node_id or self.node_id}.json"

    def announce(self, meta: Optional[dict[str, Any]] = None) -> None:
        payload = {
            "node_id": self.node_id,
            "last_seen": time.time(),
            "meta": dict(meta or {}),
        }
        self._path().write_text(_dumps(payload) + "\n", encoding="utf-8")

    def peers(self, *, include_self: bool = False) -> list[MeshPeer]:
        now = time.time()
        out: list[MeshPeer] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = _loads(path.read_text(encoding="utf-8"), {})
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            node_id = str(data.get("node_id") or path.stem)
            if not include_self and node_id == self.node_id:
                continue
            last_seen = float(data.get("last_seen") or 0)
            if self.ttl_s > 0 and (now - last_seen) > self.ttl_s:
                continue
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            out.append(MeshPeer(node_id=node_id, last_seen=last_seen, meta=dict(meta)))
        return out

    def close(self) -> None:
        try:
            self._path().unlink(missing_ok=True)
        except Exception:
            pass


@dataclass
class DurableEventBroker:
    """SQLite durable mesh: broadcast messages + per-node acks + peer heartbeats.

    Delivery is at-least-once: a node keeps seeing a message until it acks.
    Shared DB path enables multi-process same-host mesh.
    """

    db_path: Path
    node_id: str
    peer_ttl_s: float = 60.0

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def announce(self, meta: Optional[dict[str, Any]] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO mesh_peers(node_id, last_seen, meta_json)
                VALUES (?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    meta_json=excluded.meta_json
                """,
                (self.node_id, time.time(), _dumps(meta or {})),
            )
            conn.commit()

    def peers(self, *, include_self: bool = False) -> list[MeshPeer]:
        cutoff = time.time() - self.peer_ttl_s if self.peer_ttl_s > 0 else 0.0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT node_id, last_seen, meta_json FROM mesh_peers WHERE last_seen >= ?",
                (cutoff,),
            ).fetchall()
        out: list[MeshPeer] = []
        for row in rows:
            node_id = str(row["node_id"])
            if not include_self and node_id == self.node_id:
                continue
            meta = _loads(row["meta_json"], {})
            if not isinstance(meta, dict):
                meta = {}
            out.append(
                MeshPeer(
                    node_id=node_id,
                    last_seen=float(row["last_seen"]),
                    meta=dict(meta),
                )
            )
        return out

    def publish(self, event: Event, *, origin_node: str) -> bool:
        """Insert event if new. Returns True when enqueued, False if duplicate."""
        if not event.id or not event.topic:
            return False
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO mesh_messages(id, event_id, origin_node, event_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.id,
                        origin_node,
                        _dumps(event.to_dict()),
                        time.time(),
                    ),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def drain_pending(self, *, limit: int = 100) -> list[tuple[str, Event]]:
        """Return unacked remote events for this node (does not ack)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.origin_node, m.event_json
                FROM mesh_messages m
                LEFT JOIN mesh_acks a
                  ON a.event_id = m.event_id AND a.node_id = ?
                WHERE m.origin_node != ?
                  AND a.event_id IS NULL
                ORDER BY m.created_at ASC
                LIMIT ?
                """,
                (self.node_id, self.node_id, int(limit)),
            ).fetchall()
        out: list[tuple[str, Event]] = []
        for row in rows:
            try:
                data = _loads(row["event_json"], {})
                event = Event.from_dict(data if isinstance(data, dict) else {})
                if event.topic:
                    out.append((str(row["origin_node"]), event))
            except Exception:
                continue
        return out

    def ack(self, event_id: str) -> None:
        if not event_id:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO mesh_acks(event_id, node_id, acked_at)
                VALUES (?, ?, ?)
                """,
                (event_id, self.node_id, time.time()),
            )
            conn.commit()

    def pending_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM mesh_messages m
                LEFT JOIN mesh_acks a
                  ON a.event_id = m.event_id AND a.node_id = ?
                WHERE m.origin_node != ?
                  AND a.event_id IS NULL
                """,
                (self.node_id, self.node_id),
            ).fetchone()
        return int(row["n"] if row else 0)

    def close(self) -> None:
        # Leave DB on disk for peers; optionally drop our peer row.
        try:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM mesh_peers WHERE node_id = ?", (self.node_id,)
                )
                conn.commit()
        except Exception:
            pass


@dataclass
class DurableEventMeshTransport:
    """EventMeshTransport backed by DurableEventBroker (+ optional file discovery)."""

    broker: DurableEventBroker
    discovery: FilePeerRegistry | None = None
    published: int = 0

    def send(self, event: Event, *, origin_node: str) -> None:
        if self.broker.publish(event, origin_node=origin_node):
            self.published += 1
        self.heartbeat()

    def heartbeat(self, meta: Optional[dict[str, Any]] = None) -> None:
        info = dict(meta or {})
        info.setdefault("transport", "durable")
        try:
            self.broker.announce(info)
        except Exception:
            pass
        if self.discovery is not None:
            try:
                self.discovery.announce(info)
            except Exception:
                pass

    def peers(self) -> list[MeshPeer]:
        # Prefer broker membership; fall back to file registry.
        try:
            peers = self.broker.peers()
            if peers:
                return peers
        except Exception:
            pass
        if self.discovery is not None:
            return self.discovery.peers()
        return []

    def drain(self, *, limit: int = 100) -> list[tuple[str, Event]]:
        return self.broker.drain_pending(limit=limit)

    def ack(self, event_id: str) -> None:
        self.broker.ack(event_id)

    def close(self) -> None:
        try:
            self.broker.close()
        except Exception:
            pass
        if self.discovery is not None:
            try:
                self.discovery.close()
            except Exception:
                pass
