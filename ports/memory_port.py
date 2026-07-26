"""
ports/memory_port.py
====================
MemoryPort — stable interface for knowledge/RAG storage.

P0: interface only. Implementation deferred to KOS-006 (rag_store_adapter).
"""

from typing import Any, Protocol


class MemoryPort(Protocol):
    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        """Search knowledge store. Returns (score, text, source) tuples."""
        ...

    def upsert(self, text: str, source: str, metadata: dict[str, Any] | None = None) -> None:
        """Add or update a knowledge entry."""
        ...

    def list_sources(self) -> list[str]:
        ...

    def search_by_category(
        self, query: str, category: str | None = None, top_k: int = 4
    ) -> list[tuple[int, str, str]]:
        ...

    def search_multi_category(
        self, query: str, categories: list[str], top_k: int = 4
    ) -> list[tuple[int, str, str]]:
        ...

    def search_exact_id(self, query: str) -> list[tuple[int, str, str]]:
        ...
