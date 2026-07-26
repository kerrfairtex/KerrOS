"""
adapters/memory/hybrid_memory_adapter.py
========================================
MemoryPort adapter with hybrid recall: SQLite keyword/FTS + optional Qdrant vectors.
"""

from __future__ import annotations

from typing import Any

from kernel.config import load_config
from rag import store as rag_store
from adapters.memory.qdrant_vector_store import QdrantVectorStore


class HybridMemoryAdapter:
    """MemoryPort implementation using deterministic keyword + semantic vector recall."""

    def __init__(self) -> None:
        self._cfg = load_config().values
        self._vector = QdrantVectorStore(self._cfg)

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        keyword_hits = rag_store.search_fts(text, top_k=max(top_k * 2, 6))
        if not keyword_hits:
            keyword_hits = rag_store.search(text, top_k=max(top_k * 2, 6))
        vector_hits = self._vector.query(text, top_k=max(top_k * 2, 6))

        merged: dict[tuple[str, str], float] = {}
        for score, chunk, source in keyword_hits:
            key = (chunk, source)
            merged[key] = max(merged.get(key, 0.0), float(score))
        for score, chunk, source in vector_hits:
            key = (chunk, source)
            merged[key] = max(merged.get(key, 0.0), float(score) * 10.0)

        ranked = sorted(
            ((round(score), chunk, source) for (chunk, source), score in merged.items()),
            key=lambda x: x[0],
            reverse=True,
        )
        return ranked[:top_k]

    def upsert(
        self,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        rag_store.ingest_text(text, source)
        chunks = rag_store.chunk_text(text)
        self._vector.upsert(chunks, source=source, metadata=metadata)

    def list_sources(self) -> list[str]:
        return rag_store.list_sources()

    def search_by_category(
        self, query: str, category: str | None = None, top_k: int = 4
    ) -> list[tuple[int, str, str]]:
        return rag_store.search_by_category(query, category, top_k)

    def search_multi_category(
        self, query: str, categories: list[str], top_k: int = 4
    ) -> list[tuple[int, str, str]]:
        return rag_store.search_multi_category(query, categories, top_k)

    def search_exact_id(self, query: str) -> list[tuple[int, str, str]]:
        return rag_store.search_exact_id(query)

    def status(self) -> dict[str, Any]:
        return {
            "keyword_store": "sqlite_rag",
            "vector_store": self._vector.status(),
        }

