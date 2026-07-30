"""
runtime/acme_cloud_dns_sdk.py
=============================
Native cloud DNS *SDK facades* for ACME DNS-01 (ADR-033).

Default-off. Soft optional ``boto3`` Route53 and Cloudflare HTTP API
wrappers. Missing SDKs / disabled live mode fall back to in-memory
shadow records so CI never needs cloud credentials.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.acme_dns01 import Dns01Provider, InMemoryDns01Provider, _truthy


class CloudDnsSdkError(RuntimeError):
    """Native cloud DNS facade failed."""


def boto3_available() -> bool:
    try:
        import boto3  # noqa: F401

        return True
    except ImportError:
        return False


@dataclass
class SoftRoute53DnsProvider:
    """Soft Route53 TXT upsert/delete via boto3 when allow_live + installed."""

    hosted_zone_id: str = ""
    region: str = "us-east-1"
    allow_live: bool = False
    _shadow: InMemoryDns01Provider = field(default_factory=InMemoryDns01Provider)
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert_txt(self, name: str, value: str) -> None:
        self._change("UPSERT", name, value)

    def delete_txt(self, name: str) -> None:
        self._change("DELETE", name, "")

    def get_txt(self, name: str) -> list[str]:
        return self._shadow.get_txt(name)

    def _change(self, action: str, name: str, value: str) -> None:
        fqdn = str(name or "").rstrip(".") + "."
        if not self.allow_live:
            if action == "UPSERT":
                self._shadow.upsert_txt(name, value)
            else:
                self._shadow.delete_txt(name)
            out = {"ok": True, "dry_run": True, "action": action, "name": name}
            with self._lock:
                self._last = out
            return
        if not boto3_available():
            raise CloudDnsSdkError("boto3 not installed")
        if not self.hosted_zone_id:
            raise CloudDnsSdkError("hosted_zone_id required")
        try:
            import boto3

            client = boto3.client("route53", region_name=self.region)
            rr_value = f'"{value}"' if value else '""'
            client.change_resource_record_sets(
                HostedZoneId=self.hosted_zone_id,
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": action,
                            "ResourceRecordSet": {
                                "Name": fqdn,
                                "Type": "TXT",
                                "TTL": 60,
                                "ResourceRecords": [{"Value": rr_value}],
                            },
                        }
                    ]
                },
            )
            if action == "UPSERT":
                self._shadow.upsert_txt(name, value)
            else:
                self._shadow.delete_txt(name)
            out = {"ok": True, "action": action, "name": name, "provider": "route53"}
        except Exception as exc:
            out = {"ok": False, "error": str(exc), "action": action}
            with self._lock:
                self._last = out
            raise CloudDnsSdkError(str(exc)) from exc
        with self._lock:
            self._last = out

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "route53",
                "boto3": boto3_available(),
                "allow_live": self.allow_live,
                "hosted_zone_id": self.hosted_zone_id,
                "last": dict(self._last),
            }


@dataclass
class SoftCloudflareDnsProvider:
    """Soft Cloudflare DNS API via urllib (no SDK dep)."""

    api_token: str = ""
    zone_id: str = ""
    allow_live: bool = False
    timeout_s: float = 5.0
    _shadow: InMemoryDns01Provider = field(default_factory=InMemoryDns01Provider)
    _record_ids: dict[str, str] = field(default_factory=dict)
    _last: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert_txt(self, name: str, value: str) -> None:
        if not self.allow_live:
            self._shadow.upsert_txt(name, value)
            with self._lock:
                self._last = {"ok": True, "dry_run": True, "op": "upsert", "name": name}
            return
        if not self.api_token or not self.zone_id:
            raise CloudDnsSdkError("cloudflare api_token and zone_id required")
        url = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"
        body = json.dumps(
            {"type": "TXT", "name": name, "content": value, "ttl": 60}
        ).encode("utf-8")
        try:
            req = Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "kerros-acme-cf/1",
                },
            )
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                data = json.loads(resp.read().decode("utf-8"))
            rid = ""
            if isinstance(data, dict):
                res = data.get("result") or {}
                if isinstance(res, dict):
                    rid = str(res.get("id") or "")
            self._shadow.upsert_txt(name, value)
            with self._lock:
                if rid:
                    self._record_ids[name.rstrip(".").lower()] = rid
                self._last = {"ok": True, "op": "upsert", "name": name, "id": rid}
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            with self._lock:
                self._last = {"ok": False, "error": str(exc)}
            raise CloudDnsSdkError(str(exc)) from exc

    def delete_txt(self, name: str) -> None:
        key = name.rstrip(".").lower()
        if not self.allow_live:
            self._shadow.delete_txt(name)
            with self._lock:
                self._last = {"ok": True, "dry_run": True, "op": "delete", "name": name}
            return
        with self._lock:
            rid = self._record_ids.pop(key, "")
        if not rid:
            self._shadow.delete_txt(name)
            return
        url = (
            f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}"
            f"/dns_records/{rid}"
        )
        try:
            req = Request(
                url,
                method="DELETE",
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "User-Agent": "kerros-acme-cf/1",
                },
            )
            with urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310
                resp.read(1024)
            self._shadow.delete_txt(name)
            with self._lock:
                self._last = {"ok": True, "op": "delete", "name": name}
        except (HTTPError, URLError, OSError) as exc:
            with self._lock:
                self._last = {"ok": False, "error": str(exc)}
            raise CloudDnsSdkError(str(exc)) from exc

    def get_txt(self, name: str) -> list[str]:
        return self._shadow.get_txt(name)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": "cloudflare",
                "allow_live": self.allow_live,
                "zone_id": self.zone_id,
                "last": dict(self._last),
            }


@dataclass
class CloudDnsSdkConfig:
    enabled: bool = False
    provider: str = "route53"  # route53 | cloudflare
    allow_live: bool = False
    hosted_zone_id: str = ""
    region: str = "us-east-1"
    api_token: str = ""
    zone_id: str = ""

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "CloudDnsSdkConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_SDK")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        provider = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_SDK_PROVIDER")
        if provider is None:
            provider = str(data.get("provider") or "route53")

        allow_live = data.get("allow_live", False)
        env_l = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS_SDK_LIVE")
        if env_l is not None:
            allow_live = _truthy(env_l)
        else:
            allow_live = _truthy(allow_live)

        zone = os.environ.get("KERROS_ACTOR_MESH_ACME_ROUTE53_ZONE")
        if zone is None:
            zone = str(data.get("hosted_zone_id") or "")

        region = os.environ.get("KERROS_ACTOR_MESH_ACME_ROUTE53_REGION")
        if region is None:
            region = str(data.get("region") or "us-east-1")

        token = os.environ.get("KERROS_ACTOR_MESH_ACME_CF_TOKEN")
        if token is None:
            token = str(data.get("api_token") or "")

        cf_zone = os.environ.get("KERROS_ACTOR_MESH_ACME_CF_ZONE")
        if cf_zone is None:
            cf_zone = str(data.get("zone_id") or "")

        return cls(
            enabled=bool(enabled),
            provider=str(provider or "route53").strip().lower() or "route53",
            allow_live=bool(allow_live),
            hosted_zone_id=str(zone or "").strip(),
            region=str(region or "us-east-1").strip() or "us-east-1",
            api_token=str(token or "").strip(),
            zone_id=str(cf_zone or "").strip(),
        )


def build_cloud_dns_sdk_provider(
    cfg: Optional[Mapping[str, Any]] = None,
) -> Dns01Provider | None:
    sdk = CloudDnsSdkConfig.from_mapping(cfg)
    if not sdk.enabled:
        return None
    if sdk.provider in ("cloudflare", "cf"):
        return SoftCloudflareDnsProvider(
            api_token=sdk.api_token,
            zone_id=sdk.zone_id,
            allow_live=sdk.allow_live,
        )
    return SoftRoute53DnsProvider(
        hosted_zone_id=sdk.hosted_zone_id,
        region=sdk.region,
        allow_live=sdk.allow_live,
    )
