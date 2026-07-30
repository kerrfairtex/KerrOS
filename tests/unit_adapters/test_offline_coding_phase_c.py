"""ADR-052: offline coding index (rg + Fake symbols)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.code_index.code_index_adapter import (
    CodeIndexAdapter,
    is_code_index_enabled,
    probe_code_index,
)
from tools import call_tool
from tools.claw_tools import _load_safe_commands


class CodeIndexAdapterTest(unittest.TestCase):
    def test_default_off(self):
        with patch.dict(
            "os.environ",
            {"KERROS_CODE_INDEX": "0", "KERROS_OFFLINE_PROFILE": ""},
            clear=False,
        ):
            self.assertFalse(is_code_index_enabled({"code_index_enabled": False}))
            st = probe_code_index({"code_index_enabled": False})
            self.assertEqual(st["status"], "disabled")

    def test_build_and_symbol_search(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sample.py").write_text(
                "class Foo:\n    def bar(self):\n        return 1\n",
                encoding="utf-8",
            )
            idx = CodeIndexAdapter(
                {
                    "code_index_enabled": True,
                    "code_index_path": str(root / "index.json"),
                },
                workspace=root,
                base=root,
            )
            built = idx.build()
            self.assertTrue(built["ok"])
            self.assertGreaterEqual(built["symbols"], 2)
            hits = idx.search_symbols("bar")
            self.assertTrue(hits)
            self.assertEqual(hits[0]["name"], "bar")
            content = idx.search_content("return 1")
            self.assertTrue(content)


class ClawCodeToolsTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old = os.environ.get("KERROS_WORKSPACE")
        os.environ["KERROS_WORKSPACE"] = self._tmpdir.name
        from tools import claw_tools

        claw_tools.WORKSPACE = Path(self._tmpdir.name).resolve()
        (Path(self._tmpdir.name) / "demo.py").write_text(
            "def greet():\n    return 'hi'\n", encoding="utf-8"
        )

    def tearDown(self):
        if self._old is None:
            os.environ.pop("KERROS_WORKSPACE", None)
        else:
            os.environ["KERROS_WORKSPACE"] = self._old
        self._tmpdir.cleanup()

    def test_code_tools(self):
        built = call_tool("code_index_build", {})
        self.assertTrue(built.ok)
        sym = call_tool("code_symbols", {"query": "greet"})
        self.assertTrue(sym.ok)
        self.assertIn("greet", sym.output)
        search = call_tool("code_search", {"pattern": "return"})
        self.assertTrue(search.ok)

    def test_rg_allowlisted_in_config(self):
        from kernel.config import load_config

        cmds = {str(c) for c in load_config().values.get("safe_commands", [])}
        self.assertIn("rg", cmds)


class OfflineProfileCodingTest(unittest.TestCase):
    def test_profile_opts_in_rg(self):
        with patch.dict(
            "os.environ", {"KERROS_OFFLINE_PROFILE": "offline_qwen05"}, clear=False
        ):
            self.assertTrue(is_code_index_enabled({}))
            cmds = _load_safe_commands()
            self.assertIn("rg", cmds)


if __name__ == "__main__":
    unittest.main()
