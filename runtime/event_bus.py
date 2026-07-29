"""
runtime/event_bus.py
====================
Kernel event bus (Phase 3).

Typed pub/sub with history, wildcard listeners, and correlation IDs.
ServiceBus (Phase 2) remains for service lifecycle; EventBus is the
general-purpose event infrastructure for workflows, scheduler, and agents.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable


Handler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        """Rehydrate an Event (used by event-mesh transports)."""
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        return cls(
            topic=str(data.get("topic") or ""),
            payload=dict(payload),
            id=str(data.get("id") or uuid.uuid4()),
            timestamp=float(data.get("timestamp") or time.time()),
            source=str(data.get("source") or ""),
        )


@dataclass
class EventBus:
    """In-process event bus with bounded history."""

    history_limit: int = 1000
    _handlers: dict[str, list[Handler]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _history: deque[Event] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if not isinstance(self._history, deque) or self._history.maxlen != self.history_limit:
            self._history = deque(self._history, maxlen=self.history_limit)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        handlers = self._handlers.get(topic, [])
        if handler in handlers:
            handlers.remove(handler)

    def publish(
        self,
        topic: str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "",
    ) -> Event:
        event = Event(topic=topic, payload=payload or {}, source=source)
        return self.emit(event)

    def emit(self, event: Event) -> Event:
        """Dispatch an existing Event (preserves id/timestamp for mesh ingest)."""
        self._history.append(event)

        for handler in list(self._handlers.get(event.topic, [])):
            try:
                handler(event)
            except Exception:
                pass

        for handler in list(self._handlers.get("*", [])):
            try:
                handler(event)
            except Exception:
                pass

        return event

    def recent(self, count: int = 20, *, topic: str | None = None) -> list[dict[str, Any]]:
        events = list(self._history)
        if topic:
            events = [e for e in events if e.topic == topic]
        return [e.to_dict() for e in events[-count:]]

    def topics(self) -> list[str]:
        seen = set(self._handlers.keys())
        seen.update(e.topic for e in self._history)
        return sorted(seen)

    def stats(self) -> dict[str, Any]:
        by_topic: dict[str, int] = defaultdict(int)
        for event in self._history:
            by_topic[event.topic] += 1
        return {
            "events": len(self._history),
            "listeners": sum(len(v) for v in self._handlers.values()),
            "topics": self.topics(),
            "by_topic": dict(by_topic),
        }
