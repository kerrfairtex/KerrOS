"""
runtime/cmdb_vendor_sdk.py
==========================
Deep vendor CMDB SDK facades (ADR-042).

Default-off. Soft optional ``pysnow`` (ServiceNow) and Device42 HTTP SDK
wrappers. Missing SDKs / disabled live mode fall back to Fake sources so
CI never needs vendor credentials. Not a certified integration.
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

from runtime.cmdb_client import CmdbError
from runtime.cmdb_commercial import FakeDevice42Source, FakeServiceNowSource
from runtime.fleet_inventory import FleetInventory, InventoryHost
from runtime.nats_supercluster import _truthy


@runtime_checkable
class VendorCmdbSdk(Protocol):
    def fetch_hosts(self) -> list[dict[str, Any]]: ...

    def stats(self) -> dict[str, Any]: ...


def pysnow_available() -> bool:
    try:
        import pysnow  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class SoftPysnowSdk:
    """Soft ServiceNow Table API via pysnow when allow_live + installed."""

    instance: str = ""
    username: str = ""
    password: str = ""
    table: str = "cmdb_ci_server"
    allow_live: bool = False
    _shadow: FakeServiceNowSource = field(default_factory=FakeServiceNowSource)
    _last: dict[str, Any] = field(default_factory=dict)

    def fetch_hosts(self) -> list[dict[str, Any]]:
        if not self.allow_live:
            hosts = self._shadow.fetch_hosts()
            self._last = {
                "ok": True,
                "dry_run": True,
                "fetched": len(hosts),
                "pysnow": pysnow_available(),
            }
            return hosts
        if not pysnow_available():
            raise CmdbError("pysnow not installed")
        if not self.instance or not self.username:
            raise CmdbError("ServiceNow instance/username required")
        try:
            import pysnow

            client = pysnow.Client(
                instance=self.instance,
                user=self.username,
                password=self.password,
            )
            resource = client.resource(api_path=f"/table/{self.table}")
            response = resource.get(query={})
            records = list(response.all())
            normalized: list[dict[str, Any]] = []
            for rec in records:
                name = str(rec.get("name") or rec.get("host_name") or "").strip()
                address = str(
                    rec.get("ip_address") or rec.get("ip") or rec.get("dns_domain") or ""
                ).strip()
                if not name or not address:
                    continue
                normalized.append(
                    {
                        "name": name,
                        "address": address,
                        "region": str(rec.get("location") or ""),
                        "roles": [],
                        "members": ["broker"],
                        "labels": {"vendor": "servicenow", "sdk": "pysnow"},
                        "meta": {"sys_id": str(rec.get("sys_id") or "")},
                    }
                )
            self._last = {
                "ok": True,
                "fetched": len(normalized),
                "live": True,
                "sdk": "pysnow",
            }
            return normalized
        except Exception as exc:
            raise CmdbError(f"pysnow fetch failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "pysnow",
            "instance": self.instance,
            "allow_live": self.allow_live,
            "available": pysnow_available(),
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class SoftDevice42Sdk:
    """Soft Device42 REST SDK-style client when allow_live."""

    base_url: str = ""
    username: str = ""
    password: str = ""
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 15.0
    _shadow: FakeDevice42Source = field(default_factory=FakeDevice42Source)
    _last: dict[str, Any] = field(default_factory=dict)

    def fetch_hosts(self) -> list[dict[str, Any]]:
        if not self.allow_live or not self.base_url.strip():
            hosts = self._shadow.fetch_hosts()
            self._last = {"ok": True, "dry_run": True, "fetched": len(hosts)}
            return hosts
        url = self.base_url.rstrip("/") + "/api/1.0/devices/"
        headers = {
            "Accept": "application/json",
            "User-Agent": "kerros-cmdb-vendor-sdk/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            raw = data.get("Devices") or data.get("devices") or []
            if isinstance(data, list):
                raw = data
            normalized: list[dict[str, Any]] = []
            for rec in raw:
                if not isinstance(rec, dict):
                    continue
                name = str(rec.get("name") or "").strip()
                ips = rec.get("ip_addresses") or rec.get("ips") or []
                address = ""
                if isinstance(ips, list) and ips:
                    first = ips[0]
                    address = str(
                        first.get("ip") if isinstance(first, dict) else first or ""
                    ).strip()
                if not address:
                    address = str(rec.get("ip") or rec.get("address") or "").strip()
                if not name or not address:
                    continue
                normalized.append(
                    {
                        "name": name,
                        "address": address,
                        "region": str(rec.get("building") or rec.get("room") or ""),
                        "roles": [],
                        "members": ["broker"],
                        "labels": {"vendor": "device42", "sdk": "http"},
                        "meta": {"device_id": rec.get("id")},
                    }
                )
            self._last = {
                "ok": True,
                "fetched": len(normalized),
                "live": True,
                "sdk": "device42_http",
            }
            return normalized
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise CmdbError(f"device42 SDK fetch failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        return {
            "backend": "device42_sdk",
            "base_url": self.base_url,
            "allow_live": self.allow_live,
            "last": dict(self._last),
            "shadow": self._shadow.stats(),
        }


@dataclass
class VendorCmdbConfig:
    enabled: bool = False
    vendor: str = "servicenow"  # servicenow | device42
    backend: str = "fake"  # fake | pysnow | device42
    allow_live: bool = False
    instance: str = ""
    base_url: str = ""
    username: str = ""
    password: str = ""
    token: str = ""
    table: str = "cmdb_ci_server"
    auto_sync: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "VendorCmdbConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_SDK")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        vendor = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_SDK_VENDOR")
        if vendor is None:
            vendor = str(data.get("vendor") or "servicenow")

        backend = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_SDK_BACKEND")
        if backend is None:
            backend = str(data.get("backend") or "fake")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_SDK_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        instance = os.environ.get("KERROS_ACTOR_MESH_CMDB_SN_INSTANCE")
        if instance is None:
            instance = str(data.get("instance") or "")

        base_url = os.environ.get("KERROS_ACTOR_MESH_CMDB_D42_URL")
        if base_url is None:
            base_url = str(data.get("base_url") or "")

        username = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_USER")
        if username is None:
            username = str(data.get("username") or "")

        password = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_PASSWORD")
        if password is None:
            password = str(data.get("password") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_TOKEN")
        if token is None:
            token = str(data.get("token") or "")

        table = os.environ.get("KERROS_ACTOR_MESH_CMDB_SN_TABLE")
        if table is None:
            table = str(data.get("table") or "cmdb_ci_server")

        auto_sync = data.get("auto_sync", False)
        env_a = os.environ.get("KERROS_ACTOR_MESH_CMDB_VENDOR_SDK_AUTO_SYNC")
        if env_a is not None:
            auto_sync = _truthy(env_a)
        else:
            auto_sync = _truthy(auto_sync)

        return cls(
            enabled=bool(enabled),
            vendor=str(vendor or "servicenow").strip().lower() or "servicenow",
            backend=str(backend or "fake").strip().lower() or "fake",
            allow_live=bool(allow_live),
            instance=str(instance or "").strip(),
            base_url=str(base_url or "").strip(),
            username=str(username or "").strip(),
            password=str(password or "").strip(),
            token=str(token or "").strip(),
            table=str(table or "cmdb_ci_server").strip() or "cmdb_ci_server",
            auto_sync=bool(auto_sync),
        )


@dataclass
class VendorCmdbClient:
    """Pull vendor SDK hosts into FleetInventory."""

    cfg: VendorCmdbConfig
    sdk: VendorCmdbSdk = field(default_factory=FakeServiceNowSource)
    inventory: FleetInventory | None = None
    _syncs: int = 0
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def sync(self) -> dict[str, Any]:
        if not self.cfg.enabled:
            raise CmdbError("vendor CMDB SDK client disabled")
        raw_hosts = self.sdk.fetch_hosts()
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
                            "cmdb_vendor_sdk": True,
                            "vendor": self.cfg.vendor,
                            **dict(raw.get("meta") or {}),
                        },
                    )
                )
                upserted += 1
        out = {
            "ok": True,
            "vendor": self.cfg.vendor,
            "backend": self.cfg.backend,
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
                "pysnow": pysnow_available(),
                "syncs": self._syncs,
                "last": dict(self._last),
                "sdk": self.sdk.stats(),
                "inventory": self.inventory.stats() if self.inventory else {},
            }


def build_vendor_cmdb(
    cfg: Optional[Mapping[str, Any] | VendorCmdbConfig] = None,
    *,
    inventory: Optional[FleetInventory] = None,
) -> Optional[VendorCmdbClient]:
    if isinstance(cfg, VendorCmdbConfig):
        resolved = cfg
    else:
        resolved = VendorCmdbConfig.from_mapping(cfg)
    if not resolved.enabled:
        return None

    backend = resolved.backend
    vendor = resolved.vendor
    if backend == "fake":
        sdk: VendorCmdbSdk = (
            FakeDevice42Source() if vendor == "device42" else FakeServiceNowSource()
        )
    elif backend in ("pysnow", "servicenow"):
        sdk = SoftPysnowSdk(
            instance=resolved.instance,
            username=resolved.username,
            password=resolved.password,
            table=resolved.table,
            allow_live=resolved.allow_live,
        )
    elif backend == "device42":
        sdk = SoftDevice42Sdk(
            base_url=resolved.base_url,
            username=resolved.username,
            password=resolved.password,
            token=resolved.token,
            allow_live=resolved.allow_live,
        )
    elif vendor == "device42":
        sdk = SoftDevice42Sdk(
            base_url=resolved.base_url,
            username=resolved.username,
            password=resolved.password,
            token=resolved.token,
            allow_live=resolved.allow_live,
        )
    else:
        sdk = SoftPysnowSdk(
            instance=resolved.instance,
            username=resolved.username,
            password=resolved.password,
            table=resolved.table,
            allow_live=resolved.allow_live,
        )

    client = VendorCmdbClient(cfg=resolved, sdk=sdk, inventory=inventory)
    if resolved.auto_sync:
        try:
            client.sync()
        except Exception:
            pass
    return client
