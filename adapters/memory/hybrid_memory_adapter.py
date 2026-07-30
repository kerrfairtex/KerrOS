"""
adapters/memory/hybrid_memory_adapter.py
========================================
MemoryPort adapter with hybrid recall: SQLite FTS primary + optional vectors.

Vector backends (ADR-015 Qdrant, ADR-051 FAISS) are additive and default-off.
"""

from __future__ import annotations

from typing import Any

from adapters.memory.faiss_vector_store import FaissVectorStore
from adapters.memory.qdrant_vector_store import QdrantVectorStore
from kernel.config import load_config
from rag import store as rag_store

VECTOR_SCORE_WEIGHT = 10.0


class HybridMemoryAdapter:
    """MemoryPort implementation using deterministic keyword + semantic vector recall."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._cfg = dict(config) if config is not None else load_config().values
        self._qdrant = QdrantVectorStore(self._cfg)
        self._faiss = FaissVectorStore(self._cfg)

    def _vector_hits(self, text: str, top_k: int) -> list[tuple[float, str, str]]:
        hits: list[tuple[float, str, str]] = []
        hits.extend(self._faiss.query(text, top_k=top_k))
        hits.extend(self._qdrant.query(text, top_k=top_k))
        return hits

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        keyword_hits = rag_store.search_fts(text, top_k=max(top_k * 2, 6))
        if not keyword_hits:
            keyword_hits = rag_store.search(text, top_k=max(top_k * 2, 6))
        vector_hits = self._vector_hits(text, top_k=max(top_k * 2, 6))

        merged: dict[tuple[str, str], float] = {}
        for score, chunk, source in keyword_hits:
            key = (chunk, source)
            merged[key] = max(merged.get(key, 0.0), float(score))
        for score, chunk, source in vector_hits:
            key = (chunk, source)
            merged[key] = max(merged.get(key, 0.0), float(score) * VECTOR_SCORE_WEIGHT)

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
        self._faiss.upsert(chunks, source=source, metadata=metadata)
        self._qdrant.upsert(chunks, source=source, metadata=metadata)
        # ADR-017: MemoryPort mutation audit (best-effort; no raw text logged).
        try:
            from kernel.decision_log import record_decision

            record_decision(
                "memory_port",
                "upsert",
                f"source:{source}",
                "ok",
                f"chars:{len(text or '')}",
            )
        except Exception:
            pass

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
            "vector_primary": "sqlite_fts",
            "vector_stores": {
                "faiss": self._faiss.status(),
                "qdrant": self._qdrant.status(),
            },
            # Back-compat for older /status consumers.
            "vector_store": self._qdrant.status(),
        }
