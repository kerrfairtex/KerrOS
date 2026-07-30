"""
runtime/actor_supervision.py
============================
Local actor liveness / supervision foundation (ADR-020) + optional
remote process restart hooks (ADR-023).

Heartbeats + TTL table + optional ``_sys.ping`` over existing ActorMesh
request/reply. Restart hooks are callables; ADR-023 may wire them to
ServiceManager when ``remote_restart`` is enabled.
"""

from __future__ import annotations

import enum
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.actor_mesh import ActorMesh

RestartHook = Callable[[str, "ActorLiveness"], None]


class ActorHealth(enum.Enum):
    UNKNOWN = "unknown"
    ALIVE = "alive"
    SUSPECT = "suspect"
    DEAD = "dead"


@dataclass
class ActorLiveness:
    name: str
    node_id: str = ""
    last_beat: float = 0.0
    status: ActorHealth = ActorHealth.UNKNOWN
    miss_count: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    restart_hook_fired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "node_id": self.node_id,
            "last_beat": self.last_beat,
            "status": self.status.value,
            "miss_count": self.miss_count,
            "meta": dict(self.meta),
            "restart_hook_fired": self.restart_hook_fired,
        }


@dataclass
class SupervisionConfig:
    enabled: bool = False
    heartbeat_interval_s: float = 0.0  # 0 = no background thread
    ttl_s: float = 30.0
    suspect_after_s: float = 15.0
    ping_timeout_s: float = 2.0
    auto_register_ping: bool = True

    @classmethod
    def from_mapping(cls, raw: Optional[dict[str, Any]] = None) -> "SupervisionConfig":
        data = dict(raw or {})

        def _truthy(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            return str(value or "").strip().lower() in ("1", "true", "yes", "on")

        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_SUPERVISION")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        interval = data.get("heartbeat_interval_s", 0.0)
        env_i = os.environ.get("KERROS_ACTOR_MESH_HB_INTERVAL")
        if env_i is not None:
            interval = float(env_i)

        ttl = data.get("ttl_s", 30.0)
        env_t = os.environ.get("KERROS_ACTOR_MESH_HB_TTL")
        if env_t is not None:
            ttl = float(env_t)

        suspect = data.get("suspect_after_s", None)
        if suspect is None:
            suspect = float(ttl) / 2.0
        else:
            suspect = float(suspect)

        ping_t = data.get("ping_timeout_s", 2.0)
        env_p = os.environ.get("KERROS_ACTOR_MESH_PING_TIMEOUT")
        if env_p is not None:
            ping_t = float(env_p)

        auto_ping = data.get("auto_register_ping", True)
        if isinstance(auto_ping, str):
            auto_ping = _truthy(auto_ping)

        return cls(
            enabled=bool(enabled),
            heartbeat_interval_s=max(0.0, float(interval)),
            ttl_s=max(0.01, float(ttl)),
            suspect_after_s=max(0.01, float(suspect)),
            ping_timeout_s=max(0.01, float(ping_t)),
            auto_register_ping=bool(auto_ping),
        )


@dataclass
class ActorSupervisor:
    """Liveness table for named actors on an ActorMesh."""

    mesh: Any  # ActorMesh
    config: SupervisionConfig = field(default_factory=SupervisionConfig)
    on_dead: RestartHook | None = None
    _table: dict[str, ActorLiveness] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _attached: bool = field(default=False, init=False)
    _dead_events: int = field(default=0, init=False)

    def attach(self) -> None:
        if self._attached:
            return
        self._stop.clear()
        if self.config.heartbeat_interval_s > 0:
            self._thread = threading.Thread(
                target=self._loop,
                name=f"actor-sup-{getattr(self.mesh, 'node_id', 'local')}",
                daemon=True,
            )
            self._thread.start()
        self._attached = True

    def detach(self) -> None:
        self._stop.set()
        self._attached = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        interval = max(0.05, float(self.config.heartbeat_interval_s))
        while not self._stop.wait(interval):
            with self._lock:
                names = list(self._table.keys())
            for name in names:
                self.beat(name)
            self.sweep()

    def observe(self, name: str, *, node_id: str = "") -> ActorLiveness:
        key = str(name or "").strip()
        if not key:
            raise ValueError("actor name required")
        now = time.time()
        with self._lock:
            row = self._table.get(key)
            if row is None:
                row = ActorLiveness(
                    name=key,
                    node_id=node_id or str(getattr(self.mesh, "node_id", "") or ""),
                    last_beat=now,
                    status=ActorHealth.ALIVE,
                )
                self._table[key] = row
            else:
                row.last_beat = now
                row.status = ActorHealth.ALIVE
                row.miss_count = 0
                row.restart_hook_fired = False
                if node_id:
                    row.node_id = node_id
            return row

    def forget(self, name: str) -> None:
        with self._lock:
            self._table.pop(str(name or "").strip(), None)

    def beat(self, name: str, meta: Optional[dict[str, Any]] = None) -> ActorLiveness:
        key = str(name or "").strip()
        now = time.time()
        with self._lock:
            row = self._table.get(key)
            if row is None:
                row = ActorLiveness(
                    name=key,
                    node_id=str(getattr(self.mesh, "node_id", "") or ""),
                    last_beat=now,
                    status=ActorHealth.ALIVE,
                )
                self._table[key] = row
            row.last_beat = now
            row.status = ActorHealth.ALIVE
            row.miss_count = 0
            row.restart_hook_fired = False
            if meta:
                row.meta.update(meta)
            return row

    def sweep(self, now: Optional[float] = None) -> list[ActorLiveness]:
        """Advance liveness by TTL. Returns rows that transitioned to DEAD."""
        ts = float(now if now is not None else time.time())
        newly_dead: list[ActorLiveness] = []
        hooks: list[tuple[str, ActorLiveness]] = []
        with self._lock:
            for row in self._table.values():
                age = ts - float(row.last_beat or 0.0)
                prev = row.status
                if age > self.config.ttl_s:
                    row.status = ActorHealth.DEAD
                    row.miss_count += 1
                elif age > self.config.suspect_after_s:
                    row.status = ActorHealth.SUSPECT
                    row.miss_count += 1
                else:
                    row.status = ActorHealth.ALIVE
                    row.miss_count = 0
                if (
                    row.status == ActorHealth.DEAD
                    and prev != ActorHealth.DEAD
                    and not row.restart_hook_fired
                ):
                    row.restart_hook_fired = True
                    newly_dead.append(row)
                    hooks.append((row.name, row))
                    self._dead_events += 1
        if self.on_dead:
            for name, row in hooks:
                try:
                    self.on_dead(name, row)
                except Exception:
                    pass
        return newly_dead

    def ping(self, actor: str = "_sys.ping", *, timeout_s: Optional[float] = None) -> dict[str, Any]:
        """Ping a named actor (default ``_sys.ping``) via ActorMesh.request."""
        name = str(actor or "").strip() or "_sys.ping"
        timeout = (
            float(timeout_s)
            if timeout_s is not None
            else float(self.config.ping_timeout_s)
        )
        mesh = self.mesh
        if mesh is None:
            raise RuntimeError("supervisor has no mesh")
        result = mesh.request(name, {"ping": True}, timeout_s=timeout)
        # Successful ping counts as a beat for that actor name when local.
        if name in getattr(mesh, "_handlers", {}):
            self.beat(name, meta={"last_ping_ok": True})
        return dict(result or {})

    def table(self) -> dict[str, ActorLiveness]:
        with self._lock:
            return {
                k: ActorLiveness(
                    name=v.name,
                    node_id=v.node_id,
                    last_beat=v.last_beat,
                    status=v.status,
                    miss_count=v.miss_count,
                    meta=dict(v.meta),
                    restart_hook_fired=v.restart_hook_fired,
                )
                for k, v in self._table.items()
            }

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_status: dict[str, int] = {}
            for row in self._table.values():
                by_status[row.status.value] = by_status.get(row.status.value, 0) + 1
            return {
                "enabled": True,
                "attached": self._attached,
                "actors": len(self._table),
                "by_status": by_status,
                "dead_events": self._dead_events,
                "ttl_s": self.config.ttl_s,
                "suspect_after_s": self.config.suspect_after_s,
                "heartbeat_interval_s": self.config.heartbeat_interval_s,
            }
