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
