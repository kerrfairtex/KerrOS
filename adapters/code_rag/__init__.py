"""Soft production-shaped code-RAG pipeline (ADR-107)."""

from adapters.code_rag.pipeline import CodeRagAdapter, is_code_rag_enabled, probe_code_rag

__all__ = ["CodeRagAdapter", "is_code_rag_enabled", "probe_code_rag"]
