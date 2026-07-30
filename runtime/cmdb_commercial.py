"""
runtime/cmdb_commercial.py
==========================
Commercial CMDB connector foundation (ADR-040).

Default-off. Soft HTTP facades for ServiceNow / Device42-style inventory
pull into FleetInventory. Fake backends for CI; live HTTP gated by
allow_live. Not a certified ServiceNow/Device42 integration.
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

from runtime.cmdb_client import CmdbError, FakeCmdbSource
from runtime.fleet_inventory import FleetInventory, InventoryHost
from runtime.nats_supercluster import _truthy


@runtime_checkable
class CommercialCmdbSource(Protocol):
    def fetch_hosts(self) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...


@dataclass
class FakeServiceNowSource:
    """In-memory ServiceNow CMDB CI stub."""

    hosts: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "sn-broker-a",
                "address": "10.40.0.1",
                "region": "apac",
                "roles": ["edge"],
                "members": ["broker"],
                "labels": {"vendor": "servicenow", "ci_class": "cmdb_ci_server"},
                "meta": {"sys_id": "sn-001"},
            },
            {
                "name": "sn-broker-b",
                "address": "10.40.0.2",
                "region": "apac",
                "roles": ["core"],
                "members": ["broker", "leaf"],
                "labels": {"vendor": "servicenow", "ci_class": "cmdb_ci_server"},
                "meta": {"sys_id": "sn-002"},
            },
        ]
    )

    def fetch_hosts(self) -> list[dict[str, Any]]:
        return [dict(h) for h in self.hosts]

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake_servicenow", "hosts": len(self.hosts)}


@dataclass
class FakeDevice42Source:
    """In-memory Device42 device stub."""

    hosts: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {
                "name": "d42-leaf-1",
                "address": "10.41.0.1",
                "region": "emea",
                "roles": ["leaf"],
                "members": ["leaf"],
                "labels": {"vendor": "device42"},
                "meta": {"device_id": 101},
            }
        ]
    )

    def fetch_hosts(self) -> list[dict[str, Any]]:
        return [dict(h) for h in self.hosts]

    def stats(self) -> dict[str, Any]:
        return {"backend": "fake_device42", "hosts": len(self.hosts)}


@dataclass
class SoftHttpCommercialSource:
    """Soft HTTP JSON list pull; shadows Fake when not allow_live."""

    vendor: str = "servicenow"  # servicenow | device42
    url: str = ""
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 10.0
    _shadow: CommercialCmdbSource = field(default_factory=FakeServiceNowSource)
    _last: dict[str, Any] = field(default_factory=dict)

    def fetch_hosts(self) -> list[dict[str, Any]]:
        if not self.allow_live or not self.url.strip():
            hosts = self._shadow.fetch_hosts()
            self._last = {"ok": True, "dry_run": True, "fetched": len(hosts)}
            return hosts
        headers = {"Accept": "application/json", "User-Agent": "kerros-cmdb-commercial/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = Request(self.url.strip(), headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            if isinstance(data, list):
                hosts = [dict(x) for x in data if isinstance(x, dict)]
            elif isinstance(data, dict):
                # ServiceNow: result[]; Device42: Devices[] / devices[]
                raw = (
                    data.get("result")
                    or data.get("Devices")
                    or data.get("devices")
                    or data.get("hosts")
                    or []
                )
                hosts = [dict(x) for x in raw if isinstance(x, dict)]
            else:
                hosts = []
            # Normalize common vendor fields
            normalized: list[dict[str, Any]] = []
            for h in hosts:
                name = str(
                    h.get("name") or h.get("host_name") or h.get("sys_name") or ""
                ).strip()
                address = str(
                    h.get("address")
                    or h.get("ip_address")
                    or h.get("ip")
                    or h.get("host")
                    or ""
                ).strip()
                if not name or not address:
                    continue
                normalized.append(
                    {
                        "name": name,
                        "address": address,
                        "region": str(h.get("region") or h.get("location") or ""),
                        "roles": list(h.get("roles") or []),
                        "members": list(h.get("members") or ["broker"]),
                        "labels": {
                            "vendor": self.vendor,
                            **{
                                str(k): str(v)
                                for k, v in dict(h.get("labels") or {}).items()
                            },
                        },
                        "meta": {"raw_keys": sorted(h.keys())},
                    }
                )
            self._last = {
                "ok": True,
                "fetched": len(normalized),
                "vendor": self.vendor,
                "live": True,
            }
            return normalized
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise CmdbError(f"commercial CMDB fetch failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "http",
            "vendor": self.vendor,
            "url": self.url,
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class CommercialCmdbConfig:
    enabled: bool = False
    vendor: str = "servicenow"  # servicenow | device42 | generic
    backend: str = "fake"  # fake | http
    allow_live: bool = False
    url: str = ""
    token: str = ""
    auto_sync: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "CommercialCmdbConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        vendor = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR")
        if vendor is None:
            vendor = str(data.get("vendor") or "servicenow")

        backend = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        url = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL_URL")
        if url is None:
            url = str(data.get("url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        auto_sync = data.get("auto_sync", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_CMDB_COMMERCIAL_AUTO_SYNC")
        if env_a is not None:
            auto_sync = _truthy(env_a)
        else:
            auto_sync = _truthy(auto_sync)

        return cls(
            enabled=bool(enabled),
            vendor=str(vendor or "servicenow").strip().lower() or "servicenow",
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            url=str(url or "").strip(),
            token=str(token or "").strip(),
            auto_sync=bool(auto_sync),
        )


@dataclass
class CommercialCmdbClient:
    """Pull commercial CMDB hosts into FleetInventory."""

    cfg: CommercialCmdbConfig
    source: CommercialCmdbSource = field(default_factory=FakeServiceNowSource)
    inventory: FleetInventory | None = None
    _syncs: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sync(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise CmdbError("commercial CMDB client disabled")
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
                        meta={
                            "cmdb_commercial": True,
                            "vendor": self.cfg.vendor,
                            **dict(raw.get("meta") or {}),
                        },
                    )
                )
                upserted += 1
        out = {
            "ok": True,
            "vendor": self.cfg.vendor,
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
                "vendor": self.cfg.vendor,
                "backend": self.cfg.backend,
                "allow_live": self.cfg.allow_live,
                "syncs": self._syncs,
                "last": dict(self._last),
                "source": self.source.stats(),
                "inventory": self.inventory.stats() if self.inventory else {},
            }


def build_commercial_cmdb(
    cfg: Optional[Mapping[str, Any] | CommercialCmdbConfig] = None,
    *,
    inventory: Optional[FleetInventory] = None,
) -> Optional[CommercialCmdbClient]:
    if isinstance(cfg, CommercialCmdbConfig):
        resolved = cfg
    else:
        resolved = CommercialCmdbConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None
    vendor = resolved.vendor
    if resolved.backend == "http":
        if vendor == "device42":
            shadow: CommercialCmdbSource = FakeDevice42Source()
        else:
            shadow = FakeServiceNowSource()
        source: CommercialCmdbSource = SoftHttpCommercialSource(
            vendor=vendor,
            url=resolved.url,
            token=resolved.token,
            allow_live=resolved.allow_live,
            _shadow=shadow,
        )
    elif vendor == "device42":
        source = FakeDevice42Source()
    elif vendor == "generic":
        source = FakeCmdbSource()
    else:
        source = FakeServiceNowSource()
    client = CommercialCmdbClient(cfg=resolved, source=source, inventory=inventory)
    if resolved.auto_sync:
        try:
            client.sync()
        except Exception:
            pass
    return client
