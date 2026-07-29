"""
runtime/service_bus.py
======================
In-process event bus for KerrOS services (Phase 2).

Lightweight pub/sub for service lifecycle and health events.
Cross-process fanout: ``runtime/actor_mesh.py`` (C-16 / ADR-012).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


Handler = Callable[[dict[str, Any]], None]


@dataclass
class ServiceBus:
    _handlers: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> None:
        data = payload or {}
        for handler in list(self._handlers.get(topic, [])):
            try:
                handler(data)
            except Exception:
                pass

    def topics(self) -> list[str]:
        return sorted(self._handlers.keys())
