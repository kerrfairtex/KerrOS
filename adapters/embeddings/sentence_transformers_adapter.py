"""
adapters/embeddings/sentence_transformers_adapter.py
=====================================================
EmbeddingPort adapter implementing local sentence embeddings.
"""

from __future__ import annotations

import hashlib
from typing import List
from ports.embedding_port import EmbeddingPort

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class SentenceTransformersAdapter(EmbeddingPort):
    """Local SentenceTransformers embedding adapter."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self.dimension = 384
        if HAS_SENTENCE_TRANSFORMERS:
            self._model = SentenceTransformer(model_name)
        else:
            self._model = None

    def embed_query(self, text: str) -> List[float]:
        if self._model is not None:
            embedding = self._model.encode(text, convert_to_numpy=True)
            return [float(x) for x in embedding]
        return self._simulate_embedding(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._model is not None:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return [[float(x) for x in emb] for emb in embeddings]
        return [self._simulate_embedding(text) for text in texts]

    def _simulate_embedding(self, text: str) -> List[float]:
        """Generate a deterministic mock embedding vector of fixed dimension (384) using text hash."""
        vec = []
        for i in range(self.dimension):
            h = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
            val = int.from_bytes(h[:4], "big") / 4294967295.0
            vec.append(val - 0.5)
        return vec
