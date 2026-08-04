"""
ports/code_rag_port.py
======================
CodeRagPort — production-shaped Soft code-RAG pipeline (ADR-107).
"""

from __future__ import annotations

from typing import Any, Protocol


class CodeRagPort(Protocol):
    def build(self, root: str | None = None, *, full: bool = False) -> dict[str, Any]:
        """Scan + extract + index (incremental unless full=True)."""
        ...

    def retrieve(self, query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
        """Hybrid retrieve + Soft rerank with citations."""
        ...

    def build_context(self, query: str, *, top_k: int = 8, budget: int = 3500) -> dict[str, Any]:
        """Token-budget context assembly for LLM prompts."""
        ...

    def status(self) -> dict[str, Any]:
        ...
