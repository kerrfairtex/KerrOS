"""
runtime/nats_broker_fleet.py
============================
Multi-broker *fleet* manager foundation (ADR-035).

Default-off. Registers named brokers (each a ``NatsBrokerLifecycle``),
start/stop/restart the fleet, and reports aggregate health. CI uses
in-memory backends only — no live ``nats-server`` required.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.nats_broker_lifecycle import (
    BrokerLifecycleConfig,
    BrokerProcessBackend,
    InMemoryBrokerProcess,
    NatsBrokerLifecycle,
    SubprocessBrokerProcess,
    build_nats_broker_lifecycle,
)
from runtime.nats_supercluster import _truthy


class BrokerFleetError(RuntimeError):
    """Broker fleet operation failed."""


@dataclass
class BrokerFleetMember:
    name: str
    lifecycle: NatsBrokerLifecycle
    role: str = "broker"  # broker | gateway | leaf
    region: str = ""

    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "region": self.region,
            **self.lifecycle.stats(),
        }


@dataclass
class BrokerFleetConfig:
    enabled: bool = False
    members: list[dict[str, Any]] = field(default_factory=list)
    allow_spawn: bool = False
    backend: str = "memory"  # default for members lacking backend
    autostart: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "BrokerFleetConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_BROKER_FLEET")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        allow_spawn = data.get("allow_spawn", False)
        env_s = os.environ.get("KERROS_ACTOR_MESH_BROKER_FLEET_SPAWN")
        if env_s is not None:
            allow_spawn = _truthy(env_s)
        else:
            allow_spawn = _truthy(allow_spawn)

        backend = os.environ.get("KERROS_ACTOR_MESH_BROKER_FLEET_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "memory")

        autostart = data.get("autostart", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_BROKER_FLEET_AUTOSTART")
        if env_a is not None:
            autostart = _truthy(env_a)
        else:
            autostart = _truthy(autostart)

        members = list(data.get("members") or [])
        return cls(
            enabled=bool(enabled),
            members=members,
            allow_spawn=bool(allow_spawn),
            backend=str(backend or "memory").strip().lower() or "memory",
            autostart=bool(autostart),
        )


@dataclass
class BrokerFleet:
    """Named multi-broker fleet controller."""

    cfg: BrokerFleetConfig
    _members: dict[str, BrokerFleetMember] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_member(
        self,
        name: str,
        *,
        lifecycle: NatsBrokerLifecycle | None = None,
        role: str = "broker",
        region: str = "",
        member_cfg: Optional[Mapping[str, Any]] = None,
        backend: BrokerProcessBackend | None = None,
    ) -> BrokerFleetMember:
        key = str(name or "").strip()
        if not key:
            raise BrokerFleetError("member name required")
        with self._lock:
            if key in self._members:
                raise BrokerFleetError(f"duplicate member: {key}")
            if lifecycle is None:
                raw = dict(member_cfg or {})
                raw.setdefault("enabled", True)
                raw.setdefault("backend", self.cfg.backend)
                raw.setdefault("allow_spawn", self.cfg.allow_spawn)
                lc_cfg = BrokerLifecycleConfig.from_mapping({**raw, "enabled": True})
                if backend is not None:
                    be = backend
                elif lc_cfg.backend in ("subprocess", "process", "real"):
                    be = SubprocessBrokerProcess(
                        bin_name=lc_cfg.bin_name,
                        config_path=lc_cfg.config_path,
                        extra_args=list(lc_cfg.extra_args),
                        allow_spawn=lc_cfg.allow_spawn and self.cfg.allow_spawn,
                    )
                else:
                    be = InMemoryBrokerProcess(name=key)
                lifecycle = NatsBrokerLifecycle(cfg=lc_cfg, backend=be)
            member = BrokerFleetMember(
                name=key, lifecycle=lifecycle, role=role, region=region
            )
            self._members[key] = member
            return member

    def get(self, name: str) -> BrokerFleetMember | None:
        return self._members.get(str(name or "").strip())

    def start_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        with self._lock:
            items = list(self._members.items())
        for name, member in items:
            results[name] = member.lifecycle.start()
        return {"ok": all(r.get("ok") for r in results.values()) if results else True, "members": results}

    def stop_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        with self._lock:
            items = list(self._members.items())
        for name, member in items:
            results[name] = member.lifecycle.stop()
        return {"ok": True, "members": results}

    def restart_all(self) -> dict[str, Any]:
        self.stop_all()
        return self.start_all()

    def health(self) -> dict[str, Any]:
        with self._lock:
            members = [m.stats() for m in self._members.values()]
        running = sum(1 for m in members if m.get("running"))
        return {
            "members": len(members),
            "running": running,
            "healthy": running == len(members) and len(members) > 0,
            "detail": members,
        }

    def stats(self) -> dict[str, Any]:
        h = self.health()
        return {
            "enabled": self.cfg.enabled,
            "backend": self.cfg.backend,
            "allow_spawn": self.cfg.allow_spawn,
            "autostart": self.cfg.autostart,
            **h,
        }


def build_broker_fleet(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> BrokerFleet | None:
    fleet_cfg = BrokerFleetConfig.from_mapping(cfg)
    if not fleet_cfg.enabled:
        return None
    fleet = BrokerFleet(cfg=fleet_cfg)
    for raw in fleet_cfg.members:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        member_raw = dict(raw)
        member_raw.setdefault("backend", fleet_cfg.backend)
        member_raw.setdefault("allow_spawn", fleet_cfg.allow_spawn)
        # Prefer in-memory when fleet spawn disabled.
        if not fleet_cfg.allow_spawn:
            member_raw["backend"] = "memory"
            member_raw["allow_spawn"] = False
        fleet.add_member(
            name,
            role=str(raw.get("role") or "broker"),
            region=str(raw.get("region") or ""),
            member_cfg=member_raw,
        )
    if fleet_cfg.autostart:
        try:
            fleet.start_all()
        except Exception:
            pass
    return fleet
