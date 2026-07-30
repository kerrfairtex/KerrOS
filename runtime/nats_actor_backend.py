"""
runtime/nats_actor_backend.py
=============================
Optional NATS ActorMeshBackend (ADR-023).

Soft-imports ``nats`` (nats-py). Missing package → callers fall back to
socket (same pattern as pynng). Unit tests inject ``NatsClientProtocol``
fakes — no live broker required.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, runtime_checkable


class NatsBackendError(RuntimeError):
    """NATS backend failed."""


@runtime_checkable
class NatsClientProtocol(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None:
        ...

    async def subscribe(
        self, subject: str, cb: Callable[[Any], Any]
    ) -> Any:
        ...

    async def drain(self) -> None:
        ...

    async def close(self) -> None:
        ...


def nats_available() -> bool:
    try:
        import nats  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class InMemoryNatsBroker:
    """Process-local pub/sub for tests (no network)."""

    _subs: dict[str, list[Callable[[bytes], Any]]] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def handlers_for(self, subject: str) -> list[Callable[[bytes], Any]]:
        with self._lock:
            cbs = list(self._subs.get(subject, []))
            for key, handlers in self._subs.items():
                if key.endswith(">") and subject.startswith(key[:-1]):
                    cbs.extend(handlers)
            return cbs

    def subscribe_sync(
        self, subject: str, cb: Callable[[bytes], Any]
    ) -> None:
        with self._lock:
            self._subs.setdefault(subject, []).append(cb)


@dataclass
class InMemoryNatsClient:
    """Async-shaped client wrapping InMemoryNatsBroker for NatsActorBackend."""

    broker: InMemoryNatsBroker

    async def publish(self, subject: str, payload: bytes) -> None:
        for cb in self.broker.handlers_for(subject):
            result = cb(payload)
            if asyncio.iscoroutine(result):
                await result

    async def subscribe(
        self, subject: str, cb: Callable[[Any], Any]
    ) -> Any:
        def _wrap(data: bytes) -> Any:
            msg = type("Msg", (), {"data": data, "subject": subject})()
            return cb(msg)

        self.broker.subscribe_sync(subject, _wrap)
        return None

    async def drain(self) -> None:
        return None

    async def close(self) -> None:
        return None


@dataclass
class NatsActorBackend:
    """NATS subject bus implementing ActorMeshBackend.

    Subjects:
      ``{prefix}.broadcast`` — fanout
      ``{prefix}.node.{node_id}`` — optional directed (foundation uses broadcast)
    """

    url: str = "nats://127.0.0.1:4222"
    subject_prefix: str = "kerros.actor"
    node_id: str = "local"
    listen: str | None = None  # unused; kept for factory symmetry
    peers: list[str] = field(default_factory=list)
    client: NatsClientProtocol | None = None
    _inbox: queue.Queue = field(default_factory=queue.Queue, init=False, repr=False)
    _loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _owned_client: bool = field(default=False, init=False)
    _started: bool = field(default=False, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)

    def _subject_broadcast(self) -> str:
        return f"{self.subject_prefix.rstrip('.')}.broadcast"

    def _subject_node(self) -> str:
        return f"{self.subject_prefix.rstrip('.')}.node.{self.node_id}"

    def _run_coro(self, coro: Any) -> Any:
        if self._loop is None:
            raise NatsBackendError("NATS backend not started")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=10.0)

    def start(self) -> None:
        if self._started:
            return
        self._stop.clear()

        if self.client is None:
            if not nats_available():
                raise NatsBackendError(
                    "nats backend requires nats-py — pip install nats-py "
                    "(see requirements-optional.txt)"
                )

            async def _connect() -> NatsClientProtocol:
                import nats

                return await nats.connect(self.url)

            # Dedicated loop thread for the real client.
            ready: queue.Queue = queue.Queue()

            def _loop_main() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                try:
                    client = loop.run_until_complete(_connect())
                    self.client = client
                    self._owned_client = True
                    ready.put(("ok", None))
                    loop.run_forever()
                except Exception as exc:
                    ready.put(("err", exc))
                finally:
                    try:
                        loop.stop()
                    except Exception:
                        pass

            self._thread = threading.Thread(
                target=_loop_main, name="actor-nats-loop", daemon=True
            )
            self._thread.start()
            status, payload = ready.get(timeout=15.0)
            if status == "err":
                raise NatsBackendError(f"nats connect failed: {payload}") from payload
        else:
            # Injected client (tests): still need a loop for async methods.
            ready2: queue.Queue = queue.Queue()

            def _loop_injected() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready2.put(True)
                loop.run_forever()

            self._thread = threading.Thread(
                target=_loop_injected, name="actor-nats-loop", daemon=True
            )
            self._thread.start()
            ready2.get(timeout=5.0)

        assert self.client is not None
        assert self._loop is not None

        async def _on_msg(msg: Any) -> None:
            data = getattr(msg, "data", None) or b""
            if isinstance(data, str):
                data = data.encode("utf-8")
            self._inbox.put(bytes(data))

        self._run_coro(self.client.subscribe(self._subject_broadcast(), cb=_on_msg))
        self._run_coro(self.client.subscribe(self._subject_node(), cb=_on_msg))
        self._started = True
        time.sleep(0.01)

    def dial(self, peer: str) -> None:
        url = str(peer or "").strip()
        if url and url not in self.peers:
            self.peers.append(url)
        # NATS uses the broker URL; peer list is informational for stats.

    def send(self, data: bytes) -> None:
        if not self._started or self.client is None:
            raise NatsBackendError("NATS backend not started")
        self._run_coro(self.client.publish(self._subject_broadcast(), data))

    def recv(self, timeout_s: float | None = None) -> bytes | None:
        try:
            return self._inbox.get(timeout=timeout_s)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._stop.set()
        self._started = False
        if self.client is not None and self._owned_client and self._loop is not None:
            try:
                self._run_coro(self.client.drain())
            except Exception:
                pass
            try:
                self._run_coro(self.client.close())
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
        if self._owned_client:
            self.client = None
            self._owned_client = False

    def endpoints(self) -> dict[str, Any]:
        return {
            "backend": "nats",
            "url": self.url,
            "subject_prefix": self.subject_prefix,
            "node_id": self.node_id,
            "listen": self.listen,
            "peers": list(self.peers),
            "nats_available": nats_available(),
        }
