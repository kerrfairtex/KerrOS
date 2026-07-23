"""Tests for OpenClaw-style claw tools."""

import os
import tempfile
import unittest
from pathlib import Path

from tools import call_tool, list_tools, tool_names
from tools.claw_tools import get_workspace


class ClawToolsTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_workspace = os.environ.get("KERROS_WORKSPACE")
        os.environ["KERROS_WORKSPACE"] = self._tmpdir.name
        # Reset cached workspace path
        from tools import claw_tools
        claw_tools.WORKSPACE = Path(self._tmpdir.name).resolve()

    def tearDown(self):
        if self._old_workspace is None:
            os.environ.pop("KERROS_WORKSPACE", None)
        else:
            os.environ["KERROS_WORKSPACE"] = self._old_workspace
        self._tmpdir.cleanup()

    def test_list_tools_has_core_tools(self):
        names = {t["function"]["name"] for t in list_tools()}
        self.assertTrue({"read", "write", "edit", "exec", "list"}.issubset(names))

    def test_write_read_edit(self):
        w = call_tool("write", {"path": "hello.txt", "content": "hello world\n"})
        self.assertTrue(w.ok)

        r = call_tool("read", {"path": "hello.txt"})
        self.assertTrue(r.ok)
        self.assertIn("hello world", r.output)

        e = call_tool("edit", {
            "path": "hello.txt",
            "old_string": "world",
            "new_string": "claw",
        })
        self.assertTrue(e.ok)

        r2 = call_tool("read", {"path": "hello.txt"})
        self.assertIn("hello claw", r2.output)

    def test_list_dir(self):
        call_tool("write", {"path": "subdir/a.txt", "content": "a"})
        result = call_tool("list", {"path": "subdir"})
        self.assertTrue(result.ok)
        self.assertIn("a.txt", result.output)

    def test_exec_echo(self):
        result = call_tool("exec", {"command": "echo hello"})
        self.assertTrue(result.ok)
        self.assertIn("hello", result.output)

    def test_path_traversal_blocked(self):
        result = call_tool("read", {"path": "../../../etc/passwd"})
        self.assertFalse(result.ok)
        self.assertIn("escapes workspace", result.error)

    def test_remove(self):
        call_tool("write", {"path": "tmp.txt", "content": "x"})
        result = call_tool("remove", {"path": "tmp.txt"})
        self.assertTrue(result.ok)
        self.assertFalse((get_workspace() / "tmp.txt").exists())

    def test_unknown_tool(self):
        result = call_tool("nonexistent", {})
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
