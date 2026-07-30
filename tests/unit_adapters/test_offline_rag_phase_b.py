"""ADR-051: offline RAG — nomic embed resolve + FAISS soft store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.embeddings.resolve import (
    DEFAULT_OFFLINE_EMBED,
    resolve_embedding_dim,
    resolve_embedding_model,
    resolve_embedding_prefixes,
)
from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
from adapters.memory.faiss_vector_store import (
    FaissVectorStore,
    is_faiss_enabled,
    probe_faiss,
)
from adapters.memory.hybrid_memory_adapter import HybridMemoryAdapter


class EmbeddingResolveTest(unittest.TestCase):
    def test_default_minilm_dim(self):
        self.assertEqual(resolve_embedding_model({}), "all-MiniLM-L6-v2")
        self.assertEqual(resolve_embedding_dim("all-MiniLM-L6-v2"), 384)

    def test_offline_profile_nomic(self):
        with patch.dict("os.environ", {"KERROS_OFFLINE_PROFILE": "offline_qwen05"}, clear=False):
            self.assertEqual(resolve_embedding_model({}), DEFAULT_OFFLINE_EMBED)
            self.assertEqual(resolve_embedding_dim(DEFAULT_OFFLINE_EMBED), 768)
            q, d = resolve_embedding_prefixes({})
            self.assertTrue(q.startswith("search_query"))
            self.assertTrue(d.startswith("search_document"))

    def test_mock_embed_respects_dim(self):
        adapter = SentenceTransformersAdapter(
            model_name="nomic-ai/nomic-embed-text-v1.5", dimension=768
        )
        emb = adapter.embed_query("hello")
        self.assertEqual(len(emb), 768)


class FaissStoreTest(unittest.TestCase):
    def test_default_off(self):
        with patch.dict(
            "os.environ",
            {"KERROS_FAISS_ENABLED": "0", "KERROS_OFFLINE_PROFILE": ""},
            clear=False,
        ):
            self.assertFalse(is_faiss_enabled({"faiss_enabled": False}))
            store = FaissVectorStore({"faiss_enabled": False})
            self.assertFalse(store.enabled)
            self.assertEqual(store.query("x"), [])

    def test_numpy_upsert_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = {
                "faiss_enabled": True,
                "faiss_index_path": str(Path(td) / "idx.npz"),
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dim": 384,
            }
            store = FaissVectorStore(cfg, base=Path(td))
            self.assertTrue(store.enabled)
            ok = store.upsert(["alpha vector chunk", "beta other"], source="t1")
            self.assertTrue(ok)
            hits = store.query("alpha vector", top_k=2)
            self.assertTrue(hits)
            self.assertEqual(hits[0][2], "t1")
            st = probe_faiss(cfg)
            self.assertTrue(st["enabled"])


class HybridFaissTest(unittest.TestCase):
    def test_fts_still_works_with_faiss_off(self):
        adapter = HybridMemoryAdapter({"faiss_enabled": False, "qdrant_enabled": False})
        adapter.upsert("unique hybrid faiss phaseb token xyz", source="phaseb")
        hits = adapter.query("unique hybrid faiss phaseb token xyz", top_k=3)
        self.assertTrue(hits)
        st = adapter.status()
        self.assertEqual(st["vector_primary"], "sqlite_fts")
        self.assertFalse(st["vector_stores"]["faiss"]["enabled"])


if __name__ == "__main__":
    unittest.main()
