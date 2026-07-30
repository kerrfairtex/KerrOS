"""ADR-065 shell hooks, skill improve, memory nudges."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory.nudges import note_turn, pending_nudges, reset_for_tests
from tools.shell_hooks import run_shell_hook


class NudgesTest(unittest.TestCase):
    def test_emits_after_interval(self):
        reset_for_tests()
        with patch.dict(
            os.environ,
            {
                "KERROS_MEMORY_NUDGES": "1",
                "KERROS_MEMORY_NUDGE_EVERY": "3",
                "KERROS_SKILL_NUDGE_EVERY": "100",
            },
            clear=False,
        ):
            self.assertEqual(pending_nudges(), [])
            note_turn()
            note_turn()
            self.assertEqual(pending_nudges(), [])
            note_turn()
            nudges = pending_nudges()
            self.assertTrue(any("profile memory" in n for n in nudges))


class SkillImproveTest(unittest.TestCase):
    def test_record_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            stats = Path(tmp) / "usage.json"
            with patch("tools.skill_improve._stats_path", return_value=stats):
                from tools.skill_improve import record_skill_use, skill_stats

                out = record_skill_use("demo", note="worked well")
                self.assertTrue(out["ok"])
                self.assertEqual(out["uses"], 1)
                st = skill_stats("demo")
                self.assertEqual(st["stats"]["uses"], 1)


class ShellHookTest(unittest.TestCase):
    def test_run_workspace_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            script = ws / "hook.py"
            script.write_text(
                "import sys,json\n"
                "print(json.dumps({'decision':'allow'}))\n",
                encoding="utf-8",
            )
            with patch("tools.shell_hooks.get_workspace", return_value=ws):
                res = run_shell_hook("pre_tool_call", {"tool_name": "calc"}, "hook.py")
            self.assertTrue(res.get("ok"))
            self.assertEqual((res.get("parsed") or {}).get("decision"), "allow")


if __name__ == "__main__":
    unittest.main()
