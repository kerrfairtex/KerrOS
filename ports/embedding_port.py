"""
ports/embedding_port.py
========================
EmbeddingPort — stable interface for generating text embeddings.
"""

from typing import List, Protocol


class EmbeddingPort(Protocol):
    def embed_query(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text query."""
        ...

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for a list of document strings."""
        ...
