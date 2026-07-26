"""
tests/adapters/test_local_adapters.py
======================================
Tests for local ports and adapters (Storage, Database, Embeddings, LLM, Search).
"""

import unittest
import tempfile
import shutil
from pathlib import Path

from kernel import boot, shutdown, resolve
from kernel.contract import (
    SERVICE_STORAGE_PORT,
    SERVICE_DATABASE_PORT,
    SERVICE_EMBEDDING_PORT,
    SERVICE_SEARCH_PORT,
)
from adapters.storage.local_fs_adapter import LocalFSAdapter
from adapters.database.sqlite_adapter import SQLiteAdapter
from adapters.embeddings.sentence_transformers_adapter import SentenceTransformersAdapter
from adapters.llm.unsloth_adapter import UnslothAdapter
from adapters.search.duckduckgo_adapter import DuckDuckGoAdapter


class LocalFSAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.adapter = LocalFSAdapter(base_dir=self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_read_write_delete_exists(self) -> None:
        path = "test_file.txt"
        content = b"hello offline world"

        self.assertFalse(self.adapter.exists(path))
        self.adapter.write(path, content)
        self.assertTrue(self.adapter.exists(path))
        self.assertEqual(self.adapter.read(path), content)

        self.adapter.delete(path)
        self.assertFalse(self.adapter.exists(path))

    def test_path_traversal_protection(self) -> None:
        with self.assertRaises(ValueError):
            self.adapter.write("../outside.txt", b"unsafe")


class SQLiteAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_file.close()
        self.adapter = SQLiteAdapter(db_path=self.temp_file.name)

    def tearDown(self) -> None:
        Path(self.temp_file.name).unlink(missing_ok=True)

    def test_execute_fetch_all_fetch_one(self) -> None:
        self.adapter.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        self.adapter.execute("INSERT INTO users (name) VALUES (?)", ("Alice",))
        self.adapter.execute("INSERT INTO users (name) VALUES (?)", ("Bob",))

        rows = self.adapter.fetch_all("SELECT * FROM users ORDER BY name")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Alice")
        self.assertEqual(rows[1]["name"], "Bob")

        one_row = self.adapter.fetch_one("SELECT * FROM users WHERE name = ?", ("Alice",))
        self.assertIsNotNone(one_row)
        self.assertEqual(one_row["id"], 1)


class SentenceTransformersAdapterTest(unittest.TestCase):
    def test_embed_query_and_documents(self) -> None:
        adapter = SentenceTransformersAdapter()
        emb = adapter.embed_query("hello")
        self.assertEqual(len(emb), 384)
        self.assertTrue(all(isinstance(x, float) for x in emb))

        embs = adapter.embed_documents(["hello", "world"])
        self.assertEqual(len(embs), 2)
        self.assertEqual(len(embs[0]), 384)
        self.assertEqual(len(embs[1]), 384)


class UnslothAdapterTest(unittest.TestCase):
    def test_complete_and_status(self) -> None:
        adapter = UnslothAdapter()
        resp = adapter.complete("test prompt")
        self.assertIn("successful mock", resp)

        hi_resp = adapter.complete("hello")
        self.assertIn("local Qwen2.5-0.5B", hi_resp)

        status = adapter.status()
        self.assertIn("model_name", status)
        self.assertEqual(adapter.last_api_used(), "unsloth")


class DuckDuckGoAdapterTest(unittest.TestCase):
    def test_search_structure(self) -> None:
        adapter = DuckDuckGoAdapter()
        results = adapter.search("quantum computing", max_results=2)
        self.assertEqual(len(results), 2)
        for res in results:
            self.assertIn("title", res)
            self.assertIn("url", res)
            self.assertIn("snippet", res)


class KernelIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        boot()

    def tearDown(self) -> None:
        shutdown()

    def test_kernel_registers_new_ports(self) -> None:
        storage = resolve(SERVICE_STORAGE_PORT)
        self.assertIsInstance(storage, LocalFSAdapter)

        db = resolve(SERVICE_DATABASE_PORT)
        self.assertIsInstance(db, SQLiteAdapter)

        embedding = resolve(SERVICE_EMBEDDING_PORT)
        self.assertIsInstance(embedding, SentenceTransformersAdapter)

        search = resolve(SERVICE_SEARCH_PORT)
        self.assertIsInstance(search, DuckDuckGoAdapter)
