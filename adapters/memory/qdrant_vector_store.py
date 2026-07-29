"""
adapters/memory/qdrant_vector_store.py
======================================
Optional Qdrant vector recall backend used by HybridMemoryAdapter (C-18 / ADR-015).

SQLite FTS remains the primary KerrOS RAG store. Qdrant is an optional sidecar
for hybrid recall — never share OmniRoute collections (P5 / path_guard).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Optional

import requests

from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
from kernel.flags import is_true

CHUNK_PREFIX_LEN = 120
DIGEST_LEN = 64
# Stable namespace for deterministic UUID point IDs (Qdrant requires UUID/uint).
_POINT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace


def point_id_for(source: str, idx: int, chunk: str) -> str:
    """Deterministic UUID string for a chunk (idempotent upserts)."""
    digest = hashlib.sha256(
        f"{source}:{idx}:{chunk[:CHUNK_PREFIX_LEN]}".encode("utf-8")
    ).hexdigest()[:DIGEST_LEN]
    return str(uuid.uuid5(_POINT_NS, f"{source}:{idx}:{digest}"))


def resolve_qdrant_url(cfg: dict[str, Any] | None = None) -> str:
    data = cfg or {}
    return (
        os.getenv("KERROS_QDRANT_URL")
        or data.get("qdrant_url")
        or "http://127.0.0.1:6333"
    ).rstrip("/")


def is_qdrant_enabled(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or {}
    return is_true(os.getenv("KERROS_QDRANT_ENABLED", data.get("qdrant_enabled", False)))


def resolve_qdrant_api_key(cfg: dict[str, Any] | None = None) -> str:
    data = cfg or {}
    return str(
        os.getenv("KERROS_QDRANT_API_KEY") or data.get("qdrant_api_key") or ""
    ).strip()


def probe_qdrant(
    base_url: Optional[str] = None,
    *,
    api_key: Optional[str] = None,
    timeout: float = 2.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Probe Qdrant ``GET /readyz`` (fallback ``GET /collections``).

    Returns a component-shaped dict suitable for HealthMonitor.
    """
    try:
        from kernel.config import load_config

        cfg = dict(config or load_config().values)
    except Exception:
        cfg = dict(config or {})

    enabled = is_qdrant_enabled(cfg)
    url = (base_url or resolve_qdrant_url(cfg)).rstrip("/")
    key = api_key if api_key is not None else resolve_qdrant_api_key(cfg)
    headers: dict[str, str] = {}
    if key:
        headers["api-key"] = key

    result: dict[str, Any] = {
        "component": "qdrant",
        "enabled": enabled,
        "base_url": url,
        "available": False,
        "status": "disabled",
    }

    try:
        # Prefer /readyz (Qdrant ≥1.x); fall back to /collections.
        r = requests.get(f"{url}/readyz", headers=headers, timeout=timeout)
        if r.status_code == 404:
            r = requests.get(f"{url}/collections", headers=headers, timeout=timeout)
        available = r.status_code < 500
        result["available"] = available
        result["http_status"] = r.status_code
        if not enabled:
            result["status"] = "disabled"
        elif available:
            result["status"] = "ok"
        else:
            result["status"] = "unavailable"
            result["error"] = f"HTTP {r.status_code}"
    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)
        result["status"] = "disabled" if not enabled else "unavailable"

    return result


class QdrantVectorStore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.enabled = is_qdrant_enabled(cfg)
        self.url = resolve_qdrant_url(cfg)
        self.collection = (
            os.getenv("KERROS_QDRANT_COLLECTION")
            or cfg.get("qdrant_collection")
            or "kerros_memory"
        )
        from rag.path_guard import assert_qdrant_collection

        self.collection = assert_qdrant_collection(self.collection)
        self.api_key = resolve_qdrant_api_key(cfg)
        self.timeout = float(cfg.get("qdrant_timeout_s", 5))
        self._embedder = SentenceTransformersAdapter(
            model_name=str(cfg.get("qdrant_embedding_model", "all-MiniLM-L6-v2"))
        )
        self._ready = False
        self.last_error = ""

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.url}{path}"
        resp = requests.request(
            method,
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise RuntimeError(f"qdrant HTTP {resp.status_code}: {data}")
        return data

    def _ensure_collection(self) -> bool:
        if not self.enabled:
            return False
        if self._ready:
            return True
        try:
            self._request(
                "PUT",
                f"/collections/{self.collection}",
                {
                    "vectors": {
                        "size": int(getattr(self._embedder, "dimension", 384)),
                        "distance": "Cosine",
                    }
                },
            )
            self._ready = True
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def upsert(
        self,
        chunks: list[str],
        source: str,
        metadata: dict[str, Any] | None = None,
        *,
        id_offset: int = 0,
        indices: list[int] | None = None,
    ) -> bool:
        """Upsert chunk vectors. ``indices`` override per-chunk id seeds (e.g. SQLite row ids)."""
        if not self._ensure_collection() or not chunks:
            return False
        if indices is not None and len(indices) != len(chunks):
            raise ValueError("indices length must match chunks")
        try:
            vectors = self._embedder.embed_documents(chunks)
            points = []
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                point_idx = int(indices[i]) if indices is not None else id_offset + i
                payload = {
                    "text": chunk,
                    "source": source,
                    "chunk_index": point_idx,
                    **(metadata or {}),
                }
                points.append(
                    {
                        "id": point_id_for(source, point_idx, chunk),
                        "vector": vec,
                        "payload": payload,
                    }
                )
            self._request(
                "PUT",
                f"/collections/{self.collection}/points?wait=true",
                {"points": points},
            )
            self.last_error = ""
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def query(self, text: str, top_k: int = 5) -> list[tuple[float, str, str]]:
        if not self._ensure_collection():
            return []
        try:
            vector = self._embedder.embed_query(text)
            data = self._request(
                "POST",
                f"/collections/{self.collection}/points/search",
                {
                    "vector": vector,
                    "limit": top_k,
                    "with_payload": True,
                },
            )
            out: list[tuple[float, str, str]] = []
            for row in data.get("result", []) or []:
                payload = row.get("payload") or {}
                chunk = str(payload.get("text", ""))
                source = str(payload.get("source", "qdrant"))
                if not chunk:
                    continue
                out.append((float(row.get("score", 0.0)), chunk, source))
            self.last_error = ""
            return out
        except Exception as exc:
            self.last_error = str(exc)
            return []

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "ready": self._ready,
            "url": self.url,
            "collection": self.collection,
            "last_error": self.last_error,
        }
