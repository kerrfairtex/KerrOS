"""
runtime/nats_jetstream.py
=========================
Soft NATS JetStream client foundation (ADR-028).

Default-off. Soft-imports ``nats``; CI uses ``InMemoryJetStreamClient``.
Not a multi-server JetStream HA cluster manager — durable pub/sub API only.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable


class JetStreamError(RuntimeError):
    """JetStream soft client failed."""


@runtime_checkable
class JetStreamClientProtocol(Protocol):
    async def publish(
        self, subject: str, payload: bytes, *, durable: str | None = None
    ) -> Any:
        ...

    async def subscribe(
        self,
        subject: str,
        cb: Callable[[Any], Any],
        *,
        durable: str | None = None,
    ) -> Any:
        ...

    async def drain(self) -> None:
        ...

    async def close(self) -> None:
        ...


def jetstream_available() -> bool:
    try:
        import nats  # noqa: F401

        return True
    except Exception:
        return False


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class JetStreamConfig:
    enabled: bool = False
    stream: str = "kerros"
    durable: str = ""
    url: str = "nats://127.0.0.1:4222"
    subject_prefix: str = "kerros.actor"


def jetstream_config_from(raw: Optional[dict[str, Any]] = None) -> JetStreamConfig:
    data = dict(raw or {})
    enabled = data.get("enabled", False)
    env = os.environ.get("KERROS_ACTOR_MESH_JETSTREAM")
    if env is not None:
        enabled = _truthy(env)
    else:
        enabled = _truthy(enabled)

    return JetStreamConfig(
        enabled=bool(enabled),
        stream=str(
            os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_STREAM")
            or data.get("stream")
            or "kerros"
        ).strip()
        or "kerros",
        durable=str(
            os.environ.get("KERROS_ACTOR_MESH_JETSTREAM_DURABLE")
            or data.get("durable")
            or ""
        ).strip(),
        url=str(data.get("url") or "nats://127.0.0.1:4222").strip(),
        subject_prefix=str(data.get("subject_prefix") or "kerros.actor").strip()
        or "kerros.actor",
    )


@dataclass
class InMemoryJetStreamBroker:
    """Process-local durable stream (no network)."""

    streams: dict[str, list[tuple[str, bytes]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _subs: dict[str, list[Callable[[bytes, str], Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def publish_sync(
        self, stream: str, subject: str, payload: bytes
    ) -> int:
        with self._lock:
            self.streams[stream].append((subject, payload))
            seq = len(self.streams[stream])
            cbs = list(self._subs.get(subject, []))
        for cb in cbs:
            try:
                cb(payload, subject)
            except Exception:
                pass
        return seq

    def subscribe_sync(
        self, subject: str, cb: Callable[[bytes, str], Any]
    ) -> None:
        with self._lock:
            self._subs[subject].append(cb)

    def stream_len(self, stream: str) -> int:
        with self._lock:
            return len(self.streams.get(stream, []))


@dataclass
class InMemoryJetStreamClient:
    broker: InMemoryJetStreamBroker
    stream: str = "kerros"

    async def publish(
        self, subject: str, payload: bytes, *, durable: str | None = None
    ) -> Any:
        seq = self.broker.publish_sync(self.stream, subject, payload)
        return {"stream": self.stream, "seq": seq, "durable": durable or ""}

    async def subscribe(
        self,
        subject: str,
        cb: Callable[[Any], Any],
        *,
        durable: str | None = None,
    ) -> Any:
        def _wrap(data: bytes, subj: str) -> Any:
            msg = type(
                "JsMsg",
                (),
                {"data": data, "subject": subj, "durable": durable or ""},
            )()
            return cb(msg)

        self.broker.subscribe_sync(subject, _wrap)
        # Replay existing stream messages for this subject (durable-ish).
        with self.broker._lock:
            backlog = [
                (s, p)
                for (s, p) in self.broker.streams.get(self.stream, [])
                if s == subject
            ]
        for s, p in backlog:
            result = _wrap(p, s)
            if asyncio.iscoroutine(result):
                await result
        return None

    async def drain(self) -> None:
        return None

    async def close(self) -> None:
        return None


@dataclass
class JetStreamSoftClient:
    """
    Durable publish helper. Uses injected client or soft-connects via nats-py.
    """

    cfg: JetStreamConfig
    client: JetStreamClientProtocol | None = None
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _owned: bool = field(default=False, init=False)
    _started: bool = field(default=False, init=False)

    def start(self) -> None:
        if self._started:
            return
        if not self.cfg.enabled:
            raise JetStreamError("JetStream soft client disabled")

        if self.client is None:
            if not jetstream_available():
                raise JetStreamError(
                    "JetStream requires nats-py — pip install nats-py "
                    "(or inject InMemoryJetStreamClient for tests)"
                )

            ready: Any = __import__("queue").Queue()

            def _main() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                try:
                    import nats

                    async def _connect() -> Any:
                        nc = await nats.connect(self.cfg.url)
                        # Soft: obtain jetstream context; may fail on non-JS servers.
                        js = nc.jetstream()
                        return _NatsJsAdapter(nc, js, stream=self.cfg.stream)

                    self.client = loop.run_until_complete(_connect())
                    self._owned = True
                    ready.put(("ok", None))
                    loop.run_forever()
                except Exception as exc:
                    ready.put(("err", exc))

            self._thread = threading.Thread(
                target=_main, name="jetstream-soft", daemon=True
            )
            self._thread.start()
            status, payload = ready.get(timeout=15.0)
            if status == "err":
                raise JetStreamError(f"jetstream connect failed: {payload}") from payload
        else:
            ready2: Any = __import__("queue").Queue()

            def _inj() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready2.put(True)
                loop.run_forever()

            self._thread = threading.Thread(
                target=_inj, name="jetstream-soft", daemon=True
            )
            self._thread.start()
            ready2.get(timeout=5.0)

        self._started = True
        time.sleep(0.01)

    def _run(self, coro: Any) -> Any:
        if self._loop is None:
            raise JetStreamError("JetStream soft client not started")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=10.0)

    def publish(self, subject: str, payload: bytes) -> Any:
        if not self._started or self.client is None:
            raise JetStreamError("JetStream soft client not started")
        durable = self.cfg.durable or None
        return self._run(
            self.client.publish(subject, payload, durable=durable)
        )

    def close(self) -> None:
        self._started = False
        if self.client is not None and self._owned and self._loop is not None:
            try:
                self._run(self.client.drain())
            except Exception:
                pass
            try:
                self._run(self.client.close())
            except Exception:
                pass
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._loop = None
        if self._owned:
            self.client = None
            self._owned = False

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.cfg.enabled,
            "started": self._started,
            "stream": self.cfg.stream,
            "durable": self.cfg.durable,
            "url": self.cfg.url,
            "jetstream_available": jetstream_available(),
            "injected": not self._owned and self.client is not None,
        }


class _NatsJsAdapter:
    """Minimal adapter around nats-py JetStream context."""

    def __init__(self, nc: Any, js: Any, *, stream: str) -> None:
        self._nc = nc
        self._js = js
        self._stream = stream

    async def publish(
        self, subject: str, payload: bytes, *, durable: str | None = None
    ) -> Any:
        ack = await self._js.publish(subject, payload)
        return {
            "stream": getattr(ack, "stream", self._stream),
            "seq": getattr(ack, "seq", None),
            "durable": durable or "",
        }

    async def subscribe(
        self,
        subject: str,
        cb: Callable[[Any], Any],
        *,
        durable: str | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if durable:
            kwargs["durable"] = durable
        return await self._js.subscribe(subject, cb=cb, **kwargs)

    async def drain(self) -> None:
        await self._nc.drain()

    async def close(self) -> None:
        await self._nc.close()
