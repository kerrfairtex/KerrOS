"""
memory/base.py
==============
Single interface for memory operations, delegating to the concrete backend.

Existing call sites can continue using the ``kernel.access`` helpers:
    from kernel.access import memory_query, memory_search_by_category

New code should prefer ``MemoryService`` directly:
    from memory.base import MemoryService
    svc = MemoryService()
    hits = svc.query("prompt", top_k=4)
"""

from __future__ import annotations

from typing import Any


class MemoryService:
    """Facade over the configured memory backend."""

    def __init__(self) -> None:
        try:
            from kernel.access import get_memory_port

            self._port = get_memory_port()
        except Exception:
            self._port = None

    def _require_port(self) -> Any:
        if self._port is None:
            raise RuntimeError("memory port is not available")
        return self._port

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        return self._require_port().query(text, top_k=top_k)

    def upsert(
        self, text: str, source: str, metadata: dict | None = None
    ) -> None:
        if self._port is None:
            return
        try:
            self._port.upsert(text, source, metadata)
        except TypeError:
            self._port.upsert(text, source)

    def list_sources(self) -> list[str]:
        if self._port is None:
            return []
        return self._port.list_sources()

    def search_by_category(
        self, query: str, category: str | None = None, top_k: int = 4
    ):
        return self._require_port().search_by_category(
            query, category, top_k
        )

    def search_multi_category(
        self, query: str, categories: list[str], top_k: int = 4
    ):
        return self._require_port().search_multi_category(
            query, categories, top_k
        )

    def search_exact_id(self, query: str):
        return self._require_port().search_exact_id(query)

    def status(self) -> dict[str, Any]:
        if self._port is None:
            return {"enabled": False}
        try:
            return self._port.status()
        except Exception:
            return {"enabled": False}
