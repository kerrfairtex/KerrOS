"""
memory/service.py
=================
High-level memory service used by CLI and agents.

This wraps ``memory.base.MemoryService`` and adds session/profile helpers
so callers do not need to import multiple ``memory.*`` modules directly.
"""

from __future__ import annotations

from typing import Any


class MemoryService:
    """Unified facade for semantic memory, sessions, and profile access."""

    def __init__(self) -> None:
        self._semantic = _SemanticMemory()
        self._sessions = _SessionMemory()
        self._profile = _ProfileMemory()
        self._vector = _VectorMemory()

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[int, str, str]]:
        return self._vector.query(text, top_k=top_k)

    def upsert(self, text: str, source: str, metadata: dict | None = None) -> None:
        self._vector.upsert(text, source, metadata)

    def list_sources(self) -> list[str]:
        return self._vector.list_sources()

    def search_by_category(
        self, query: str, category: str | None = None, top_k: int = 4
    ):
        return self._vector.search_by_category(query, category, top_k)

    def search_multi_category(
        self, query: str, categories: list[str], top_k: int = 4
    ):
        return self._vector.search_multi_category(query, categories, top_k)

    def search_exact_id(self, query: str):
        return self._vector.search_exact_id(query)

    def status(self) -> dict[str, Any]:
        return self._vector.status()

    def recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._sessions.recent_sessions(limit=limit)

    def browse_session(
        self, session_id: str, *, limit: int = 30
    ) -> dict[str, Any]:
        return self._sessions.browse_session(session_id, limit=limit)

    def search_sessions(
        self, query: str, *, top_k: int = 8
    ) -> list[dict[str, Any]]:
        return self._sessions.search_sessions(query, top_k=top_k)

    def get_profile(self) -> dict[str, Any]:
        return self._profile.get_profile()

    def update_profile(self, key: str, value: Any) -> None:
        self._profile.update_profile(key, value)

    def semantic_context(self) -> str:
        return self._semantic.context_string()

    def ingest_file(self, path: str) -> None:
        p = _expand(path)
        if not p.exists():
            return
        text = p.read_text(encoding="utf-8", errors="ignore")
        self.upsert(text, p.name)


def _expand(path: str):
    from pathlib import Path

    return Path(path).expanduser()


class _VectorMemory:
    def __init__(self) -> None:
        from memory.base import MemoryService

        self._svc = MemoryService()

    def query(self, text: str, *, top_k: int = 5):
        return self._svc.query(text, top_k=top_k)

    def upsert(self, text: str, source: str, metadata: dict | None = None) -> None:
        return self._svc.upsert(text, source, metadata)

    def list_sources(self) -> list[str]:
        return self._svc.list_sources()

    def search_by_category(
        self, query: str, category: str | None = None, top_k: int = 4
    ):
        return self._svc.search_by_category(query, category, top_k)

    def search_multi_category(
        self, query: str, categories: list[str], top_k: int = 4
    ):
        return self._svc.search_multi_category(query, categories, top_k)

    def search_exact_id(self, query: str):
        return self._svc.search_exact_id(query)

    def status(self) -> dict[str, Any]:
        return self._svc.status()


class _SessionMemory:
    def recent_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        try:
            from memory.session_store import list_sessions

            return list_sessions(limit=limit)
        except Exception:
            return []

    def browse_session(
        self, session_id: str, *, limit: int = 30
    ) -> dict[str, Any]:
        try:
            from memory.session_store import browse_session

            return browse_session(session_id, limit=limit)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def search_sessions(
        self, query: str, *, top_k: int = 8
    ) -> list[dict[str, Any]]:
        try:
            from memory.session_store import search_sessions

            return search_sessions(query, top_k=top_k)
        except Exception:
            return []


class _ProfileMemory:
    def get_profile(self) -> dict[str, Any]:
        try:
            from memory.manager import get_profile

            return get_profile()
        except Exception:
            return {}

    def update_profile(self, key: str, value: Any) -> None:
        try:
            from memory.manager import update_profile

            update_profile(key, value)
        except Exception:
            pass


class _SemanticMemory:
    def context_string(self) -> str:
        try:
            from memory.semantic import build_context_string

            return build_context_string() or ""
        except Exception:
            return ""
