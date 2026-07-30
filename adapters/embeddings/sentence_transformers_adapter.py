"""
adapters/embeddings/sentence_transformers_adapter.py
=====================================================
EmbeddingPort adapter implementing local sentence embeddings (ADR-051).
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

from adapters.embeddings.resolve import (
    nomic_trust_remote_code,
    resolve_embedding_dim,
    resolve_embedding_model,
    resolve_embedding_prefixes,
)
from ports.embedding_port import EmbeddingPort

try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class SentenceTransformersAdapter(EmbeddingPort):
    """Local SentenceTransformers embedding adapter."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        *,
        dimension: Optional[int] = None,
        config: dict | None = None,
        query_prefix: Optional[str] = None,
        document_prefix: Optional[str] = None,
    ) -> None:
        cfg = dict(config or {})
        self.model_name = model_name or resolve_embedding_model(cfg)
        self.dimension = int(
            dimension if dimension is not None else resolve_embedding_dim(self.model_name, cfg)
        )
        q_def, d_def = resolve_embedding_prefixes(cfg, model_name=self.model_name)
        self.query_prefix = query_prefix if query_prefix is not None else q_def
        self.document_prefix = (
            document_prefix if document_prefix is not None else d_def
        )
        self._model = None
        if HAS_SENTENCE_TRANSFORMERS:
            kwargs = {}
            if nomic_trust_remote_code(self.model_name):
                kwargs["trust_remote_code"] = True
            try:
                self._model = SentenceTransformer(self.model_name, **kwargs)
                # Prefer live model dim when available.
                try:
                    self.dimension = int(self._model.get_sentence_embedding_dimension())
                except Exception:
                    pass
            except Exception:
                self._model = None

    def embed_query(self, text: str) -> List[float]:
        payload = f"{self.query_prefix}{text}" if self.query_prefix else text
        if self._model is not None:
            embedding = self._model.encode(payload, convert_to_numpy=True)
            return [float(x) for x in embedding]
        return self._simulate_embedding(payload)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        payloads = [
            f"{self.document_prefix}{t}" if self.document_prefix else t for t in texts
        ]
        if self._model is not None:
            embeddings = self._model.encode(payloads, convert_to_numpy=True)
            return [[float(x) for x in emb] for emb in embeddings]
        return [self._simulate_embedding(t) for t in payloads]

    def _simulate_embedding(self, text: str) -> List[float]:
        """Deterministic mock embedding (no HF download) for CI / soft Fake."""
        vec = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
            val = int.from_bytes(h[:4], "big") / 4294967295.0
            vec.append(val - 0.5)
        return vec
