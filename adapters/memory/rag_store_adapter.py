"""
adapters/memory/rag_store_adapter.py
====================================
MemoryPort adapter wrapping rag/store.py (KOS-006).
"""

from __future__ import annotations

from typing import Any

from rag import store as rag_store


class RagStoreAdapter:
    """MemoryPort implementation over the existing RAG keyword store."""

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        return rag_store.search(text, top_k=top_k)

    def upsert(
        self,
        text: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        rag_store.ingest_text(text, source)
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
