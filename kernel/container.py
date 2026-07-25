"""
kernel/container.py
===================
Minimal dependency injection container for kernel services and ports.

Services are registered by name during boot and resolved by callers or
adapters. Singletons are cached; transient factories create a new instance
on every resolve().
"""

from __future__ import annotations

from typing import Any, Callable

from kernel.contract import ServiceAlreadyRegisteredError, ServiceNotFoundError

Factory = Callable[[], Any]


class Container:
    def __init__(self) -> None:
        self._factories: dict[str, Factory] = {}
        self._singletons: dict[str, bool] = {}
        self._cache: dict[str, Any] = {}

    def register(
        self,
        name: str,
        factory: Factory | Any,
        *,
        singleton: bool = True,
    ) -> None:
        if name in self._factories:
            raise ServiceAlreadyRegisteredError(f"service already registered: {name}")

        if callable(factory):
            self._factories[name] = factory
        else:
            value = factory
            self._factories[name] = lambda v=value: v

        self._singletons[name] = singleton

    def resolve(self, name: str) -> Any:
        if name not in self._factories:
            raise ServiceNotFoundError(f"service not registered: {name}")

        if self._singletons.get(name, True):
            if name not in self._cache:
                self._cache[name] = self._factories[name]()
            return self._cache[name]

        return self._factories[name]()

    def has(self, name: str) -> bool:
        return name in self._factories

    def clear(self) -> None:
        self._factories.clear()
        self._singletons.clear()
        self._cache.clear()

    def names(self) -> list[str]:
        return sorted(self._factories.keys())
