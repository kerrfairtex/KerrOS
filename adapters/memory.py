"""
adapters/memory.py
==================
Shim: proposed future path for memory adapter namespace.
Current implementation: adapters/memory/hybrid_memory_adapter.py and related modules.
"""

from adapters.memory.hybrid_memory_adapter import HybridMemoryAdapter
from adapters.memory.faiss_vector_store import FaissVectorStore
from adapters.memory.qdrant_vector_store import QdrantVectorStore
from adapters.memory.rag_store_adapter import RagStoreAdapter

__all__ = [
    "HybridMemoryAdapter",
    "FaissVectorStore",
    "QdrantVectorStore",
    "RagStoreAdapter",
]
