"""
memory/qdrant.py
================
Shim: proposed future path for Qdrant memory backend.
Current implementation: adapters/memory/qdrant_vector_store.py
"""

from adapters.memory.qdrant_vector_store import QdrantVectorStore

__all__ = ["QdrantVectorStore"]
