"""
runtime/nats_jetstream_cluster.py
=================================
JetStream multi-URL failover foundation (ADR-029).

Default-off. Tries ``servers`` in order on connect / publish failure.
Not a NATS Supercluster manager — client-side HA only. Tests use
``InMemoryClusterJetStream`` (no live broker).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from runtime.nats_jetstream import (
    InMemoryJetStreamBroker,
    InMemoryJetStreamClient,
    JetStreamClientProtocol,
    JetStreamConfig,
    JetStreamError,
    JetStreamSoftClient,
    _truthy,
    jetstream_available,
    jetstream_config_from,
)


def _parse_servers(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(s).strip() for s in raw if str(s).strip()]
    return []


@dataclass
class JetStreamClusterConfig:
    enabled: bool = False
    servers: list[str] = field(default_factory=list)
    stream: str = "kerros"
    durable: str = ""
    subject_prefix: str = "kerros.actor"
    connect_timeout_s: float = 2.0
    failover_retries: int = 2

    @classmethod
    def from_mapping(cls, raw: Optional[dict[str, Any]] = None) -> "JetStreamClusterConfig":
        data = dict(raw or {})
        enabled = data.get("enabled", False)
        env = os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_CLUSTER")
        if env is not None:
            enabled = _truthy(env)
        else:
            enabled = _truthy(enabled)

        servers = _parse_servers(
            os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_SERVERS")
            if os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_SERVERS") is not None
            else data.get("servers")
        )
        # Fall back to single url from parent jetstream config.
        if not servers:
            url = str(data.get("url") or "").strip()
            if url:
                servers = [url]

        base = jetstream_config_from(data)
        retries = data.get("failover_retries", 2)
        env_r = os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_FAILOVER_RETRIES")
        if env_r is not None and str(env_r).strip().isdigit():
            retries = int(env_r)

        return cls(
            enabled=bool(enabled),
            servers=servers,
            stream=base.stream,
            durable=base.durable,
            subject_prefix=base.subject_prefix,
            connect_timeout_s=max(0.1, float(data.get("connect_timeout_s") or 2.0)),
            failover_retries=max(0, int(retries)),
        )


@dataclass
class _GuardedInMemoryClient:
    cluster: "InMemoryClusterJetStream"
    url: str
    inner: InMemoryJetStreamClient

    async def publish(
        self, subject: str, payload: bytes, *, durable: str | None = None
    ) -> Any:
        if self.url in self.cluster._fail:
            raise JetStreamError(f"server unavailable: {self.url}")
        return await self.inner.publish(subject, payload, durable=durable)

    async def subscribe(
        self,
        subject: str,
        cb: Any,
        *,
        durable: str | None = None,
    ) -> Any:
        if self.url in self.cluster._fail:
            raise JetStreamError(f"server unavailable: {self.url}")
        return await self.inner.subscribe(subject, cb, durable=durable)

    async def drain(self) -> None:
        await self.inner.drain()

    async def close(self) -> None:
        await self.inner.close()


@dataclass
class InMemoryClusterJetStream:
    """
    Multi-broker in-memory cluster for tests.

    ``fail_primary`` makes the first server raise until ``heal_primary``.
    """

    servers: list[str] = field(default_factory=lambda: ["mem://a", "mem://b"])
    stream: str = "kerros"
    _brokers: dict[str, InMemoryJetStreamBroker] = field(default_factory=dict)
    _fail: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        for url in self.servers:
            self._brokers[url] = InMemoryJetStreamBroker()

    def fail_primary(self) -> None:
        if self.servers:
            self._fail.add(self.servers[0])

    def heal_primary(self) -> None:
        if self.servers:
            self._fail.discard(self.servers[0])

    def client_for(self, url: str) -> JetStreamClientProtocol:
        if url in self._fail:
            raise JetStreamError(f"server unavailable: {url}")
        broker = self._brokers.get(url)
        if broker is None:
            raise JetStreamError(f"unknown server: {url}")
        inner = InMemoryJetStreamClient(broker, stream=self.stream)
        return _GuardedInMemoryClient(cluster=self, url=url, inner=inner)

    def stream_len(self, url: str) -> int:
        b = self._brokers.get(url)
        return b.stream_len(self.stream) if b else 0


@dataclass
class JetStreamClusterClient:
    """
    Client-side HA: connect/publish across ``servers`` with failover.
    """

    cfg: JetStreamClusterConfig
    cluster: InMemoryClusterJetStream | None = None  # test inject
    _active_url: str = ""
    _client: JetStreamSoftClient | None = None
    _failovers: int = 0
    _attempts: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _started: bool = False

    def start(self) -> None:
        if self._started:
            return
        if not self.cfg.enabled:
            raise JetStreamError("JetStream cluster disabled")
        if not self.cfg.servers and self.cluster is None:
            raise JetStreamError("JetStream cluster requires servers list")
        self._connect_next(start_index=0)
        self._started = True

    def _server_list(self) -> list[str]:
        if self.cluster is not None:
            return list(self.cluster.servers)
        return list(self.cfg.servers)

    def _connect_next(self, *, start_index: int = 0) -> None:
        servers = self._server_list()
        if not servers:
            raise JetStreamError("no JetStream servers configured")
        last_exc: Exception | None = None
        n = len(servers)
        for offset in range(n):
            idx = (start_index + offset) % n
            url = servers[idx]
            self._attempts += 1
            try:
                if self.cluster is not None:
                    injected = self.cluster.client_for(url)
                    soft = JetStreamSoftClient(
                        cfg=JetStreamConfig(
                            enabled=True,
                            stream=self.cfg.stream,
                            durable=self.cfg.durable,
                            url=url,
                            subject_prefix=self.cfg.subject_prefix,
                        ),
                        client=injected,
                    )
                    soft.start()
                else:
                    if not jetstream_available():
                        raise JetStreamError(
                            "JetStream cluster requires nats-py "
                            "(or inject InMemoryClusterJetStream)"
                        )
                    soft = JetStreamSoftClient(
                        cfg=JetStreamConfig(
                            enabled=True,
                            stream=self.cfg.stream,
                            durable=self.cfg.durable,
                            url=url,
                            subject_prefix=self.cfg.subject_prefix,
                        )
                    )
                    soft.start()
                with self._lock:
                    if self._client is not None:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                    self._client = soft
                    self._active_url = url
                return
            except Exception as exc:
                last_exc = exc
                continue
        raise JetStreamError(
            f"all JetStream servers failed: {last_exc}"
        ) from last_exc

    def publish(self, subject: str, payload: bytes) -> Any:
        if not self._started or self._client is None:
            raise JetStreamError("JetStream cluster not started")
        retries = max(0, int(self.cfg.failover_retries))
        last_exc: Exception | None = None
        servers = self._server_list()
        try:
            start_idx = servers.index(self._active_url) if self._active_url in servers else 0
        except ValueError:
            start_idx = 0

        for attempt in range(retries + 1):
            try:
                return self._client.publish(subject, payload)
            except Exception as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                self._failovers += 1
                next_idx = (start_idx + attempt + 1) % max(1, len(servers))
                self._connect_next(start_index=next_idx)
        raise JetStreamError(f"publish failed after failover: {last_exc}") from last_exc

    def close(self) -> None:
        self._started = False
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            self._active_url = ""

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.cfg.enabled,
                "started": self._started,
                "active_url": self._active_url,
                "servers": self._server_list(),
                "failovers": self._failovers,
                "attempts": self._attempts,
                "stream": self.cfg.stream,
                "cluster_mode": True,
            }
