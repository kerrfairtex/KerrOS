"""
runtime/fleet_inventory.py
==========================
Fleet host *inventory* / CMDB-lite foundation (ADR-038).

Default-off. Registers hosts with roles/regions/labels and can export
remote-fleet host specs for ADR-037 orchestration. In-memory + optional
JSON file persistence. Not a full CMDB.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from runtime.nats_supercluster import _truthy


class FleetInventoryError(RuntimeError):
    """Fleet inventory operation failed."""


@dataclass
class InventoryHost:
    name: str
    address: str
    region: str = ""
    roles: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=lambda: ["broker"])
    labels: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "region": self.region,
            "roles": list(self.roles),
            "members": list(self.members),
            "labels": dict(self.labels),
            "meta": dict(self.meta),
        }

    def to_remote_fleet_host(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "host": self.address,
            "members": list(self.members) or ["broker"],
            "region": self.region,
        }


@dataclass
class FleetInventoryConfig:
    enabled: bool = False
    store_path: str = "data/fleet_inventory.json"
    allow_persist: bool = False
    hosts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_mapping(
        cls,
        raw: Optional[Mapping[str, Any]] = None,
        *,
        base: Optional[Path] = None,
    ) -> "FleetInventoryConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_FLEET_INVENTORY")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        store = os.environ.get("KERROS_ACTOR_MESH_FLEET_INVENTORY_PATH")
        if store is None:
            store = str(data.get("store_path") or "data/fleet_inventory.json")
        path = Path(store)
        if not path.is_absolute() and base is not None:
            path = Path(base) / path

        persist = data.get("allow_persist", False)
        env_p = os.environ.get("KERROS_ACTOR_MESH_FLEET_INVENTORY_PERSIST")
        if env_p is not None:
            persist = _truthy(env_p)
        else:
            persist = _truthy(persist)

        return cls(
            enabled=bool(enabled),
            store_path=str(path),
            allow_persist=bool(persist),
            hosts=list(data.get("hosts") or []),
        )


@dataclass
class FleetInventory:
    """In-memory host inventory with optional JSON persistence."""

    cfg: FleetInventoryConfig
    _hosts: dict[str, InventoryHost] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert(self, host: InventoryHost) -> None:
        name = str(host.name or "").strip()
        if not name:
            raise FleetInventoryError("host name required")
        if not str(host.address or "").strip():
            raise FleetInventoryError("host address required")
        with self._lock:
            self._hosts[name] = host

    def get(self, name: str) -> InventoryHost | None:
        return self._hosts.get(str(name or "").strip())

    def list_hosts(self, *, role: str = "", region: str = "") -> list[InventoryHost]:
        with self._lock:
            items = list(self._hosts.values())
        if role:
            items = [h for h in items if role in h.roles]
        if region:
            items = [h for h in items if h.region == region]
        return items

    def remove(self, name: str) -> bool:
        with self._lock:
            return self._hosts.pop(str(name or "").strip(), None) is not None

    def export_remote_fleet_hosts(self) -> list[dict[str, Any]]:
        return [h.to_remote_fleet_host() for h in self.list_hosts()]

    def persist(self) -> dict[str, Any]:
        if not self.cfg.allow_persist:
            return {"ok": False, "skipped": True, "error": "persist disabled"}
        path = Path(self.cfg.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": time.time(),
            "hosts": [h.to_dict() for h in self.list_hosts()],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(path), "hosts": len(payload["hosts"])}

    def load(self) -> dict[str, Any]:
        path = Path(self.cfg.store_path)
        if not path.is_file():
            return {"ok": False, "skipped": True, "error": "no store file"}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            hosts = data.get("hosts") if isinstance(data, dict) else []
            count = 0
            for raw in hosts or []:
                if not isinstance(raw, dict):
                    continue
                self.upsert(
                    InventoryHost(
                        name=str(raw.get("name") or ""),
                        address=str(raw.get("address") or raw.get("host") or ""),
                        region=str(raw.get("region") or ""),
                        roles=[str(r) for r in (raw.get("roles") or [])],
                        members=[str(m) for m in (raw.get("members") or ["broker"])],
                        labels={str(k): str(v) for k, v in dict(raw.get("labels") or {}).items()},
                        meta=dict(raw.get("meta") or {}),
                    )
                )
                count += 1
            return {"ok": True, "loaded": count}
        except (OSError, json.JSONDecodeError, FleetInventoryError) as exc:
            return {"ok": False, "error": str(exc)}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "hosts": len(self._hosts),
                "allow_persist": self.cfg.allow_persist,
                "store_path": self.cfg.store_path,
                "by_region": _count_by(self._hosts.values(), "region"),
            }


def _count_by(hosts, attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in hosts:
        key = str(getattr(h, attr, "") or "unknown")
        out[key] = out.get(key, 0) + 1
    return out


def build_fleet_inventory(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    base: Optional[Path] = None,
) -> FleetInventory | None:
    inv_cfg = FleetInventoryConfig.from_mapping(cfg, base=base)
    if not inv_cfg.enabled:
        return None
    inv = FleetInventory(cfg=inv_cfg)
    for raw in inv_cfg.hosts:
        try:
            inv.upsert(
                InventoryHost(
                    name=str(raw.get("name") or ""),
                    address=str(raw.get("address") or raw.get("host") or ""),
                    region=str(raw.get("region") or ""),
                    roles=[str(r) for r in (raw.get("roles") or [])],
                    members=[str(m) for m in (raw.get("members") or ["broker"])],
                    labels={str(k): str(v) for k, v in dict(raw.get("labels") or {}).items()},
                    meta=dict(raw.get("meta") or {}),
                )
            )
        except FleetInventoryError:
            continue
    if Path(inv_cfg.store_path).is_file():
        inv.load()
    return inv
