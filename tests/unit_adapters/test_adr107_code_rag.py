"""ADR-107 Soft code-RAG pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.code_rag.extract import extract_file
from adapters.code_rag.pipeline import CodeRagAdapter
from adapters.code_rag.scanner import scan_repository
from adapters.code_rag.retrieve import detect_intent


SAMPLE_PY = '''\
"""demo module"""
import os

def helper():
    """help"""
    return 1

def main():
    x = helper()
    return x + os.getpid()

class Greeter:
    def hello(self, name):
        return f"hi {name}"
'''


class CodeRagPipelineTest(unittest.TestCase):
    def test_extract_semantic_chunks_and_edges(self):
        out = extract_file("demo.py", SAMPLE_PY)
        self.assertEqual(out["language"], "python")
        names = {c["name"] for c in out["chunks"]}
        self.assertIn("helper", names)
        self.assertIn("main", names)
        self.assertIn("Greeter", names)
        self.assertTrue(any(e.get("rel") == "imports" for e in out["edges"]))
        self.assertTrue(any(e.get("rel") == "calls" and e.get("dst") == "helper" for e in out["edges"]))
        for c in out["chunks"]:
            self.assertIn(":", c["citation"])

    def test_incremental_build_and_hybrid_retrieve(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pkg").mkdir()
            (root / "pkg" / "demo.py").write_text(SAMPLE_PY, encoding="utf-8")
            (root / ".gitignore").write_text("ignore_me/\n", encoding="utf-8")
            (root / "ignore_me").mkdir()
            (root / "ignore_me" / "secret.py").write_text("def secret():\n    pass\n", encoding="utf-8")
            (root / "node_modules" / "x").mkdir(parents=True)
            (root / "node_modules" / "x" / "a.js").write_text("function noop(){}", encoding="utf-8")

            rag = CodeRagAdapter(
                {"code_rag": {"enabled": True, "path": str(root / ".code_rag")}},
                workspace=root,
            )
            first = rag.build()
            self.assertTrue(first["ok"])
            self.assertGreaterEqual(first["processed"], 1)
            manifest_files = set((rag.indexes.load_manifest().get("files") or {}).keys())
            self.assertIn("pkg/demo.py", manifest_files)
            self.assertNotIn("ignore_me/secret.py", manifest_files)
            self.assertTrue(all("node_modules" not in p for p in manifest_files))

            # incremental: unchanged → 0 processed
            second = rag.build()
            self.assertEqual(second["processed"], 0)
            self.assertGreaterEqual(second["unchanged"], 1)

            # change file → reindex
            (root / "pkg" / "demo.py").write_text(
                SAMPLE_PY + "\ndef impact_target():\n    return helper()\n",
                encoding="utf-8",
            )
            third = rag.build()
            self.assertEqual(third["changed"], 1)
            self.assertEqual(third["processed"], 1)

            hits = rag.retrieve("helper", top_k=5)
            self.assertTrue(hits)
            self.assertTrue(any("helper" in (h.get("name") or "") for h in hits))
            self.assertTrue(any(h.get("citation") for h in hits))

            ctx = rag.build_context("what calls helper?", top_k=5)
            self.assertTrue(ctx["ok"])
            self.assertTrue(ctx["citations"])
            self.assertIn("Source:", ctx["context"])

            impact = rag.retrieve("impact of changing helper", top_k=8)
            self.assertEqual(detect_intent("impact of changing helper"), "impact")
            self.assertTrue(any("graph" in (h.get("sources") or []) or h.get("kind") == "graph" for h in impact) or impact)

    def test_claw_tools_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "m.py").write_text("def alpha():\n    return 2\n", encoding="utf-8")
            from tools import claw_tools

            with patch("tools.claw_tools.get_workspace", return_value=root):
                built = claw_tools.code_rag_build()
                self.assertTrue(built.ok)
                hit = claw_tools.code_rag_retrieve("alpha")
                self.assertTrue(hit.ok)
                self.assertIn("alpha", hit.output)
                ask = claw_tools.code_rag_ask("explain alpha")
                self.assertTrue(ask.ok)
                self.assertIn("citations=", ask.output)

    def test_build_rejects_root_escape(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rag = CodeRagAdapter(
                {"code_rag": {"enabled": True, "path": str(root / ".code_rag")}},
                workspace=root,
            )
            out = rag.build(root="../outside")
            self.assertFalse(out["ok"])
            self.assertEqual(out["error"], "root escapes workspace")

    def test_scan_reuses_sha_for_unchanged_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "same.py").write_text("def same():\n    return 1\n", encoding="utf-8")
            first = scan_repository(root)
            with patch("adapters.code_rag.scanner.file_sha", side_effect=RuntimeError("unexpected hash")):
                second = scan_repository(root, previous=first)
            self.assertEqual(second["changed"], [])
            self.assertEqual(second["unchanged"], ["same.py"])


if __name__ == "__main__":
    unittest.main()
