"""Tests for claw CLI command parsing."""

import os
import tempfile
import unittest
from pathlib import Path

from tools.claw_cli import detect_claw_tool, run_claw_tool


class ClawCliTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_workspace = os.environ.get("KERROS_WORKSPACE")
        os.environ["KERROS_WORKSPACE"] = self._tmpdir.name
        from tools import claw_tools
        claw_tools.WORKSPACE = Path(self._tmpdir.name).resolve()

    def tearDown(self):
        if self._old_workspace is None:
            os.environ.pop("KERROS_WORKSPACE", None)
        else:
            os.environ["KERROS_WORKSPACE"] = self._old_workspace
        self._tmpdir.cleanup()

    def test_detect_read(self):
        name, args = detect_claw_tool("/read hello.txt")
        self.assertEqual(name, "read")
        self.assertEqual(args["path"], "hello.txt")

    def test_detect_exec(self):
        name, args = detect_claw_tool("/exec echo hi")
        self.assertEqual(name, "exec")
        self.assertEqual(args["command"], "echo hi")

    def test_detect_code_rag_status_retrieves(self):
        name, args = detect_claw_tool("/code-rag status")
        self.assertEqual(name, "code_rag_retrieve")
        self.assertEqual(args["query"], "status")

    def test_detect_tool_json(self):
        name, args = detect_claw_tool('/tool write {"path":"a.txt","content":"x"}')
        self.assertEqual(name, "write")
        self.assertEqual(args["path"], "a.txt")

    def test_run_via_cli(self):
        out = run_claw_tool("write", {"path": "t.txt", "content": "data"})
        self.assertIn("[write]", out)
        read_out = run_claw_tool("read", {"path": "t.txt"})
        self.assertIn("data", read_out)


if __name__ == "__main__":
    unittest.main()
