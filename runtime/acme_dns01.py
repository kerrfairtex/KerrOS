"""
runtime/acme_dns01.py
=====================
ACME DNS-01 challenge solver foundation (ADR-031).

Default-off. Computes RFC 8555 DNS-01 TXT values and stores them in an
in-memory zone (CI-safe). Does **not** call cloud DNS APIs — operators
wire a real provider later; this validates challenge plumbing.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


class AcmeDns01Error(RuntimeError):
    """DNS-01 solver failed."""


def dns01_txt_value(key_authorization: str) -> str:
    """
    RFC 8555 §8.4: base64url(SHA-256(keyAuthorization)).
    """
    digest = hashlib.sha256(str(key_authorization or "").encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def dns01_name(domain: str) -> str:
    host = str(domain or "").strip().rstrip(".")
    if not host:
        raise AcmeDns01Error("domain required")
    if host.startswith("_acme-challenge."):
        return host
    return f"_acme-challenge.{host}"


@runtime_checkable
class Dns01Provider(Protocol):
    def upsert_txt(self, name: str, value: str) -> None: ...

    def delete_txt(self, name: str) -> None: ...

    def get_txt(self, name: str) -> list[str]: ...


@dataclass
class InMemoryDns01Provider:
    """CI-safe in-memory TXT zone."""

    _records: dict[str, list[str]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def upsert_txt(self, name: str, value: str) -> None:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            self._records[key] = [str(value)]

    def delete_txt(self, name: str) -> None:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            self._records.pop(key, None)

    def get_txt(self, name: str) -> list[str]:
        key = str(name or "").rstrip(".").lower()
        with self._lock:
            return list(self._records.get(key) or [])

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"provider": "memory", "names": len(self._records)}


@dataclass
class AcmeDns01Config:
    enabled: bool = False
    provider: str = "memory"

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]] = None) -> "AcmeDns01Config":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS01")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        provider = os.environ.get("KERROS_ACTOR_MESH_ACME_DNS01_PROVIDER")
        if provider is None:
            provider = str(data.get("provider") or "memory")

        return cls(
            enabled=bool(enabled),
            provider=str(provider or "memory").strip().lower() or "memory",
        )


@dataclass
class AcmeDns01Solver:
    """Put/clear DNS-01 TXT challenges via a provider."""

    cfg: AcmeDns01Config
    provider: Dns01Provider = field(default_factory=InMemoryDns01Provider)
    _active: dict[str, str] = field(default_factory=dict)  # domain -> txt
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _puts: int = 0
    _clears: int = 0

    def put_challenge(self, domain: str, key_authorization: str) -> dict[str, str]:
        name = dns01_name(domain)
        value = dns01_txt_value(key_authorization)
        self.provider.upsert_txt(name, value)
        with self._lock:
            self._active[str(domain).strip().rstrip(".").lower()] = value
            self._puts += 1
        return {"name": name, "value": value, "domain": domain}

    def clear_challenge(self, domain: str) -> None:
        name = dns01_name(domain)
        self.provider.delete_txt(name)
        with self._lock:
            self._active.pop(str(domain).strip().rstrip(".").lower(), None)
            self._clears += 1

    def get_challenge(self, domain: str) -> str | None:
        name = dns01_name(domain)
        values = self.provider.get_txt(name)
        return values[0] if values else None

    def verify_local(self, domain: str, key_authorization: str) -> bool:
        expected = dns01_txt_value(key_authorization)
        return self.get_challenge(domain) == expected

    def stats(self) -> dict[str, Any]:
        with self._lock:
            provider_stats = (
                self.provider.stats() if hasattr(self.provider, "stats") else {}
            )
            return {
                "enabled": self.cfg.enabled,
                "provider": self.cfg.provider,
                "active": len(self._active),
                "puts": self._puts,
                "clears": self._clears,
                "provider_stats": provider_stats,
            }


def build_acme_dns01_solver(
    cfg: Optional[Mapping[str, Any]] = None,
    *,
    provider: Dns01Provider | None = None,
) -> AcmeDns01Solver | None:
    dns_cfg = AcmeDns01Config.from_mapping(cfg)
    if not dns_cfg.enabled:
        return None
    if dns_cfg.provider not in ("memory", "mem", "inmemory"):
        # Only memory provider ships; unknown names still get memory with note.
        pass
    return AcmeDns01Solver(
        cfg=dns_cfg,
        provider=provider or InMemoryDns01Provider(),
    )
