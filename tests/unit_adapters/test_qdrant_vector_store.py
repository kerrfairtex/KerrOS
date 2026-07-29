"""Qdrant vector store + probe tests (C-18 / ADR-015)."""

from __future__ import annotations

import unittest
from unittest import mock

from adapters.memory.qdrant_vector_store import (
    QdrantVectorStore,
    point_id_for,
    probe_qdrant,
)


class PointIdTest(unittest.TestCase):
    def test_deterministic_uuid(self):
        a = point_id_for("src", 1, "hello world")
        b = point_id_for("src", 1, "hello world")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 36)
        self.assertNotEqual(a, point_id_for("src", 2, "hello world"))


class QdrantVectorStoreMockTest(unittest.TestCase):
    def test_disabled_noop(self):
        store = QdrantVectorStore({"qdrant_enabled": False})
        self.assertFalse(store.enabled)
        self.assertFalse(store.upsert(["a"], "s"))
        self.assertEqual(store.query("a"), [])

    @mock.patch("adapters.memory.qdrant_vector_store.requests.request")
    def test_ensure_upsert_query(self, req):
        def _resp(status=200, payload=None):
            r = mock.Mock()
            r.status_code = status
            r.content = b"{}" if payload is None else b"1"
            r.json.return_value = payload if payload is not None else {}
            return r

        req.side_effect = [
            _resp(200, {}),  # ensure collection
            _resp(200, {}),  # upsert
            _resp(
                200,
                {
                    "result": [
                        {
                            "score": 0.9,
                            "payload": {"text": "chunk-a", "source": "demo"},
                        }
                    ]
                },
            ),
        ]

        store = QdrantVectorStore(
            {
                "qdrant_enabled": True,
                "qdrant_url": "http://127.0.0.1:6333",
                "qdrant_collection": "kerros_memory",
            }
        )
        self.assertTrue(store.upsert(["chunk-a"], "demo", indices=[42]))
        hits = store.query("chunk", top_k=3)
        self.assertEqual(hits[0][1], "chunk-a")
        self.assertEqual(hits[0][2], "demo")
        # PUT collection + PUT points + POST search
        self.assertEqual(req.call_count, 3)
        upsert_payload = req.call_args_list[1].kwargs["json"]
        self.assertIn("points", upsert_payload)
        self.assertEqual(len(upsert_payload["points"][0]["id"]), 36)
        self.assertEqual(
            upsert_payload["points"][0]["id"],
            point_id_for("demo", 42, "chunk-a"),
        )

    @mock.patch("adapters.memory.qdrant_vector_store.requests.get")
    def test_probe_disabled_but_reachable(self, get):
        r = mock.Mock()
        r.status_code = 200
        get.return_value = r
        out = probe_qdrant(
            "http://127.0.0.1:6333",
            config={"qdrant_enabled": False},
        )
        self.assertFalse(out["enabled"])
        self.assertEqual(out["status"], "disabled")
        self.assertTrue(out["available"])

    @mock.patch("adapters.memory.qdrant_vector_store.requests.get")
    def test_probe_enabled_ok(self, get):
        r = mock.Mock()
        r.status_code = 200
        get.return_value = r
        out = probe_qdrant(
            "http://127.0.0.1:6333",
            config={"qdrant_enabled": True},
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["status"], "ok")


class MigrateDryRunTest(unittest.TestCase):
    def test_iter_and_count(self):
        import tempfile
        from pathlib import Path
        import os

        from rag import store as rag_store

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "rag_store.db"
            # Point store at temp db
            old = rag_store.DB_PATH
            rag_store.DB_PATH = str(db)
            try:
                rag_store._ensure_schema()
                rag_store.ingest_text(("alpha beta gamma " * 40) + ("delta " * 80), "unit-src")
                n = rag_store.count_chunks(source="unit-src")
                self.assertGreaterEqual(n, 1)
                rows = list(rag_store.iter_chunks(source="unit-src", limit=5))
                self.assertGreaterEqual(len(rows), 1)
                self.assertLessEqual(len(rows), 5)
                self.assertEqual(rows[0][2], "unit-src")
            finally:
                rag_store.DB_PATH = old


if __name__ == "__main__":
    unittest.main()
