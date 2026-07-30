"""
runtime/acme_cloud_dns.py
=========================
Cloud DNS provider foundation for ACME DNS-01 (ADR-032).

Default-off. Ships an in-memory cloud facade and an opt-in HTTP webhook
provider (operator-owned bridge to Route53/Cloudflare/etc.). No AWS/GCP
SDKs — soft urllib only.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.acme_dns01 import (
    AcmeDns01Config,
    AcmeDns01Solver,
    Dns01Provider,
    InMemoryDns01Provider,
    _truthy,
)


class AcmeCloudDnsError(RuntimeError):
    """Cloud DNS provider failed."""


@dataclass
class FakeCloudDnsProvider:
    """Cloud-shaped in-memory TXT store (CI)."""

    zone: str = "example.com"
    _records: dict[str, list[str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _calls: int = 0

    def upsert_txt(self, name: str, value: str) -> None:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            self._records[key] = [str(value)]
            self._calls += 1

    def delete_txt(self, name: str) -> None:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            self._records.pop(key, None)
            self._calls += 1

    def get_txt(self, name: str) -> list[str]:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            return list(self._records.get(key) or [])

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "fake_cloud",
                "zone": self.zone,
                "names": len(self._records),
                "calls": self._calls,
            }


@dataclass
class WebhookCloudDnsProvider:
    """
    Soft HTTP webhook DNS bridge.
    POSTs JSON ``{op, name, value}`` to ``webhook_url`` when allow_live.
    """

    webhook_url: str
    token: str = ""
    allow_live: bool = False
    timeout_s: float = 5.0
    _shadow: InMemoryDns01Provider = field(default_factory=InMemoryDns01Provider)
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _post(self, op: str, name: str, value: str = "") -> dict[str, Any]:
        if not self.allow_live:
            # Shadow locally so solvers still work in dry mode.
            if op == "upsert":
                self._shadow.upsert_txt(name, value)
            elif op == "delete":
                self._shadow.delete_txt(name)
            out = {"ok": True, "dry_run": True, "op": op, "name": name}
            with self._lock:
                self._last = dict(out)
            return out
        url = str(self.webhook_url or "").strip()
        if not url:
            raise AcmeCloudDnsError("webhook_url required for live cloud DNS")
        payload = json.dumps({"op": op, "name": name, "value": value}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "kerros-acme-cloud-dns/1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            req = Request(url, data=payload, method="POST", headers=headers)
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                out = {
                    "ok": True,
                    "status": getattr(resp, "status", 200),
                    "op": op,
                    "name": name,
                }
        except HTTPError as exc:
            out = {"ok": False, "status": exc.code, "error": str(exc), "op": op}
        except (URLError, OSError, ValueError) as exc:
            out = {"ok": False, "error": str(exc), "op": op}
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "op": op}
        # Keep shadow in sync on success for local verify.
        if out.get("ok"):
            if op == "upsert":
                self._shadow.upsert_txt(name, value)
            elif op == "delete":
                self._shadow.delete_txt(name)
        with self._lock:
            self._last = dict(out)
        if not out.get("ok"):
            raise AcmeCloudDnsError(out.get("error") or "webhook failed")
        return out

    def upsert_txt(self, name: str, value: str) -> None:
        self._post("upsert", name, value)

    def delete_txt(self, name: str) -> None:
        self._post("delete", name, "")

    def get_txt(self, name: str) -> list[str]:
        return self._shadow.get_txt(name)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "webhook",
                "webhook_url": self.webhook_url,
                "allow_live": self.allow_live,
                "last": dict(self._last),
                "shadow": self._shadow.stats(),
            }


@dataclass
class AcmeCloudDnsConfig:
    enabled: bool = False
    provider: str = "fake"  # fake | webhook | memory
    webhook_url: str = ""
    webhook_token: str = ""
    allow_live: bool = False
    zone: str = ""
    timeout_s: float = 5.0

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeCloudDnsConfig":
        data = dict(raw or {})
        # Prefer nested cloud block under dns01, or standalone mapping.
        cloud = data.get("cloud") if isinstance(data.get("cloud"), dict) else data
        cloud = dict(cloud or {})

        enabled = cloud.get("enabled", data.get("enabled", False))
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_CLOUD_DNS")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        provider = os.environ.get("KERROS_ACTOR_MESH_ACME_CLOUD_DNS_PROVIDER")
        if provider is None:
            provider = str(
                cloud.get("provider") or data.get("provider") or "fake"
            )

        webhook = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_WEBHOOK")
        if webhook is None:
            webhook = str(cloud.get("webhook_url") or data.get("webhook_url") or "")

        token = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_WEBHOOK_TOKEN")
        if token is None:
            token = str(cloud.get("webhook_token") or data.get("webhook_token") or "")

        allow_live = cloud.get("allow_live", data.get("allow_live", False))
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_CLOUD_DNS_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        zone = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_ZONE")
        if zone is None:
            zone = str(cloud.get("zone") or data.get("zone") or "")

        timeout = cloud.get("timeout_s", data.get("timeout_s", 5.0))
        env_t = os.environ.get("KERROS_ACTOR_MESH_ACME_CLOUD_DNS_TIMEOUT")
        if env_t is not None:
            timeout = float(env_t)

        return cls(
            enabled=bool(enabled),
            provider=str(provider or "fake").strip().lower() or "fake",
            webhook_url=str(webhook or "").strip(),
            webhook_token=str(token or "").strip(),
            allow_live=bool(allow_live),
            zone=str(zone or "").strip(),
            timeout_s=max(0.5, float(timeout or 5.0)),
        )


def build_cloud_dns_provider(
    cfg: Optional[Mapping[str, Any]] = None,
) -> Dns01Provider | None:
    cloud_cfg = AcmeCloudDnsConfig.from_mapping(cfg)
    if not cloud_cfg.enabled:
        return None
    if cloud_cfg.provider in ("webhook", "http"):
        return WebhookCloudDnsProvider(
            webhook_url=cloud_cfg.webhook_url,
            token=cloud_cfg.webhook_token,
            allow_live=cloud_cfg.allow_live,
            timeout_s=cloud_cfg.timeout_s,
        )
    if cloud_cfg.provider in ("memory", "mem", "inmemory"):
        return InMemoryDns01Provider()
    return FakeCloudDnsProvider(zone=cloud_cfg.zone or "example.com")


def build_acme_dns01_with_cloud(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    provider: Dns01Provider | None = None,
) -> AcmeDns01Solver | None:
    """
    Build DNS-01 solver, preferring an explicit/cloud provider when configured.
    """
    data = dict(cfg or {})
    dns_cfg = AcmeDns01Config.from_mapping(data)
    if not dns_cfg.enabled:
        return None
    if provider is not None:
        return AcmeDns01Solver(cfg=dns_cfg, provider=provider)

    cloud_raw = data.get("cloud") if isinstance(data.get("cloud"), dict) else {}
    # Enable cloud when provider name implies it or cloud.enabled.
    provider_name = str(dns_cfg.provider or "memory").lower()
    cloud_enabled = _truthy(cloud_raw.get("enabled", False)) or provider_name in (
        "webhook",
        "fake",
        "cloud",
        "fake_cloud",
    )
    if cloud_enabled or provider_name in ("webhook", "fake", "cloud", "fake_cloud"):
        merged = {
            **cloud_raw,
            "enabled": True,
            "provider": cloud_raw.get("provider")
            or ("webhook" if provider_name == "webhook" else "fake"),
            "webhook_url": cloud_raw.get("webhook_url") or data.get("webhook_url") or "",
            "webhook_token": cloud_raw.get("webhook_token")
            or data.get("webhook_token")
            or "",
            "allow_live": cloud_raw.get("allow_live", False),
        }
        cloud_prov = build_cloud_dns_provider(merged)
        if cloud_prov is not None:
            return AcmeDns01Solver(cfg=dns_cfg, provider=cloud_prov)

    return AcmeDns01Solver(cfg=dns_cfg, provider=InMemoryDns01Provider())
