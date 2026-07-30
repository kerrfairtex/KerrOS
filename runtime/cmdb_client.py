"""
runtime/cmdb_client.py
======================
CMDB integration foundation (ADR-039).

Default-off. Syncs hosts from a Fake CMDB or soft HTTP CMDB API into
``FleetInventory``. Not a full CMDB product — sync client only.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.fleet_inventory import FleetInventory, InventoryHost
from runtime.nats_supercluster import _truthy


class CmdbError(RuntimeError):
    """CMDB client failed."""


@runtime_checkable
class CmdbSource(Protocol):
    def fetch_hosts(self) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeCmdbSource:
    """In-memory CMDB for CI."""

    hosts: list[dict[str, Any]] = field(default_factory=list)
    _fetches: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def set_hosts(self, hosts: list[dict[str, Any]]) -> None:
        with self._lock:
            self.hosts = [dict(h) for h in hosts]

    def fetch_hosts(self) -> list[dict[str, Any]]:
        with self._lock:
            self._fetches += 1
            return [dict(h) for h in self.hosts]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"backend": "fake", "hosts": len(self.hosts), "fetches": self._fetches}


@dataclass
class SoftHttpCmdbSource:
    """Soft GET JSON list of hosts from a CMDB HTTP API."""

    url: str
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 5.0
    _shadow: FakeCmdbSource = field(default_factory=FakeCmdbSource)
    _last: dict[str, Any] = field(default_factory=dict)

    def fetch_hosts(self) -> list[dict[str, Any]]:
        if not self.allow_live:
            hosts = self._shadow.fetch_hosts()
            self._last = {"ok": True, "dry_run": True, "hosts": len(hosts)}
            return hosts
        url = str(self.url or "").strip()
        if not url:
            raise CmdbError("CMDB url required")
        headers = {"User-Agent": "kerros-cmdb/1", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            req = Request(url, method="GET", headers=headers)
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                hosts = data.get("hosts") or data.get("items") or []
            elif isinstance(data, list):
                hosts = data
            else:
                hosts = []
            out = [dict(h) for h in hosts if isinstance(h, dict)]
            self._last = {"ok": True, "hosts": len(out), "backend": "http"}
            return out
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._last = {"ok": False, "error": str(exc)}
            raise CmdbError(str(exc)) from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "http",
            "url": self.url,
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class CmdbClientConfig:
    enabled: bool = False
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    url: str = ""
    token: str = ""
    auto_sync: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "CmdbClientConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_CMDB")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        backend = os.environ.get("KERROS_ACTOR_MESH_CMDB_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_CMDB_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        url = os.environ.get("KERROS_ACTOR_MESH_CMDB_URL")
        if url is None:
            url = str(data.get("url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_CMDB_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        auto_sync = data.get("auto_sync", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_CMDB_AUTO_SYNC")
        if env_a is not None:
            auto_sync = _truthy(env_a)
        else:
            auto_sync = _truthy(auto_sync)

        return cls(
            enabled=bool(enabled),
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            url=str(url or "").strip(),
            token=str(token or "").strip(),
            auto_sync=bool(auto_sync),
        )


@dataclass
class CmdbSyncClient:
    """Pull CMDB hosts into a FleetInventory."""

    cfg: CmdbClientConfig
    source: CmdbSource = field(default_factory=FakeCmdbSource)
    inventory: FleetInventory | None = None
    _syncs: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sync(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise CmdbError("CMDB client disabled")
        raw_hosts = self.source.fetch_hosts()
        upserted = 0
        if self.inventory is not None:
            for raw in raw_hosts:
                name = str(raw.get("name") or "").strip()
                address = str(raw.get("address") or raw.get("host") or "").strip()
                if not name or not address:
                    continue
                self.inventory.upsert(
                    InventoryHost(
                        name=name,
                        address=address,
                        region=str(raw.get("region") or ""),
                        roles=[str(r) for r in (raw.get("roles") or [])],
                        members=[str(m) for m in (raw.get("members") or ["broker"])],
                        labels={
                            str(k): str(v)
                            for k, v in dict(raw.get("labels") or {}).items()
                        },
                        meta={"cmdb": True, **dict(raw.get("meta") or {})},
                    )
                )
                upserted += 1
        out = {
            "ok": True,
            "fetched": len(raw_hosts),
            "upserted": upserted,
            "at": time.time(),
        }
        with self._lock:
            self._syncs += 1
            self._last = dict(out)
        return out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "syncs": self._syncs,
                "last": dict(self._last),
                "source": self.source.stats(),
                "inventory": self.inventory.stats() if self.inventory else {},
            }


def build_cmdb_sync_client(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    inventory: FleetInventory | None = None,
    source: CmdbSource | None = None,
) -> CmdbSyncClient | None:
    ccfg = CmdbClientConfig.from_mapping(cfg)
    if not ccfg.enabled:
        return None
    if source is not None:
        src = source
    elif ccfg.backend == "http":
        src = SoftHttpCmdbSource(
            url=ccfg.url, token=ccfg.token, allow_live=ccfg.allow_live
        )
    else:
        src = FakeCmdbSource(hosts=list((cfg or {}).get("hosts") or []))
    client = CmdbSyncClient(cfg=ccfg, source=src, inventory=inventory)
    if ccfg.auto_sync:
        try:
            client.sync()
        except Exception:
            pass
    return client
