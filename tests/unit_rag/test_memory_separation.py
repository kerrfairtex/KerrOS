"""P5: OmniRoute memory stays separate from KerrOS RAG."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from rag.path_guard import (
    MemorySeparationError,
    assert_kerros_memory_path,
    assert_qdrant_collection,
    looks_like_omniroute_path,
)

ROOT = Path(__file__).resolve().parents[2]


class PathGuardTest(unittest.TestCase):
    def test_allows_kerros_rag_path(self):
        path = str(ROOT / "data" / "rag_store.db")
        self.assertEqual(assert_kerros_memory_path(path, label="DB_PATH"), path)

    def test_rejects_deploy_omniroute(self):
        with self.assertRaises(MemorySeparationError):
            assert_kerros_memory_path(
                ROOT / "deploy" / "omniroute" / "data" / "store.db",
                label="DB_PATH",
            )

    def test_rejects_named_volume_marker(self):
        self.assertTrue(looks_like_omniroute_path("/var/lib/docker/volumes/kerros-omniroute-data/_data"))
        with self.assertRaises(MemorySeparationError):
            assert_kerros_memory_path(
                "/var/lib/docker/volumes/kerros-omniroute-data/_data/db",
                label="knowledge_root",
            )

    def test_rejects_container_data_dir(self):
        with self.assertRaises(MemorySeparationError):
            assert_kerros_memory_path("/app/data/omni.db", label="DB_PATH")

    def test_qdrant_collection_default(self):
        self.assertEqual(assert_qdrant_collection(None), "kerros_memory")
        self.assertEqual(assert_qdrant_collection("kerros_memory"), "kerros_memory")

    def test_qdrant_rejects_omniroute_named(self):
        with self.assertRaises(MemorySeparationError):
            assert_qdrant_collection("omniroute_vectors")


class MemorySeparationArtifactsTest(unittest.TestCase):
    def test_check_script(self):
        script = ROOT / "scripts" / "check_memory_separation.py"
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("OK:", proc.stdout)

    def test_doc_and_compose(self):
        doc = (ROOT / "docs" / "MEMORY_SEPARATION.md").read_text(encoding="utf-8")
        self.assertIn("rag_store.db", doc)
        self.assertIn("kerros_memory", doc)
        compose = (ROOT / "deploy" / "omniroute" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("kerros-omniroute-data", compose)
        self.assertIn("MEMORY_SEPARATION", compose)
        self.assertNotIn("rag_store.db", compose)


if __name__ == "__main__":
    unittest.main()
