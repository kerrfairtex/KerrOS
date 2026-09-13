"""
memory/faiss.py
===============
Shim: proposed future path for FAISS memory backend.
Current implementation: adapters/memory/faiss_vector_store.py
"""

from adapters.memory.faiss_vector_store import FaissVectorStore

__all__ = ["FaissVectorStore"]
