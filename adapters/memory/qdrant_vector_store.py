"""
adapters/memory/qdrant_vector_store.py
======================================
Optional Qdrant vector recall backend used by HybridMemoryAdapter.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import requests

from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
from kernel.flags import is_true

CHUNK_PREFIX_LEN = 120
DIGEST_LEN = 64


class QdrantVectorStore:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        enabled_cfg = cfg.get("qdrant_enabled", False)
        self.enabled = is_true(os.getenv("KERROS_QDRANT_ENABLED", enabled_cfg))
        self.url = (
            os.getenv("KERROS_QDRANT_URL")
            or cfg.get("qdrant_url")
            or "http://127.0.0.1:6333"
        ).rstrip("/")
        self.collection = (
            os.getenv("KERROS_QDRANT_COLLECTION")
            or cfg.get("qdrant_collection")
            or "kerros_memory"
        )
        from rag.path_guard import assert_qdrant_collection

        self.collection = assert_qdrant_collection(self.collection)
        self.api_key = os.getenv("KERROS_QDRANT_API_KEY") or cfg.get("qdrant_api_key") or ""
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

    def upsert(self, chunks: list[str], source: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self._ensure_collection() or not chunks:
            return False
        try:
            vectors = self._embedder.embed_documents(chunks)
            points = []
            for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
                digest = hashlib.sha256(
                    f"{source}:{idx}:{chunk[:CHUNK_PREFIX_LEN]}".encode("utf-8")
                ).hexdigest()[:DIGEST_LEN]
                points.append(
                    {
                        # Deterministic ID ties source+chunk index+content hash to make
                        # retries idempotent and minimize collision risk across updates.
                        # Use deterministic string IDs to minimize collision risk.
                        "id": f"{source}:{idx}:{digest}",
                        "vector": vec,
                        "payload": {
                            "text": chunk,
                            "source": source,
                            **(metadata or {}),
                        },
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
