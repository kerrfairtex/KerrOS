"""Hermes-behavior port: hooks, message policy, session FTS, skills, pipeline."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ToolHooksTest(unittest.TestCase):
    def test_scope_gate_is_default_pre_hook(self):
        from tools.tool_hooks import list_hooks, reset_hooks_for_tests

        reset_hooks_for_tests()
        names = list_hooks()["pre"]
        self.assertEqual(names[0], "scope_gate")

    def test_custom_pre_hook_can_deny(self):
        from tools.tool_hooks import (
            register_pre_tool_call,
            reset_hooks_for_tests,
            run_pre_tool_call,
        )

        reset_hooks_for_tests()

        def deny_calc(tool, args):
            if tool == "calc":
                return False, "no calc"
            return True, "ok"

        register_pre_tool_call("deny_calc", deny_calc, prepend=True)
        ok, reason, hook = run_pre_tool_call("calc", "1+1")
        self.assertFalse(ok)
        self.assertEqual(hook, "deny_calc")
        self.assertIn("no calc", reason)


class MessagePolicyTest(unittest.TestCase):
    def test_repairs_duplicate_roles_and_compresses(self):
        from core.message_policy import prepare_history, validate_alternation

        msgs = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "c"},
        ]
        fixed, warnings = validate_alternation(msgs)
        self.assertTrue(any("duplicate_role" in w for w in warnings))
        self.assertEqual(fixed[0]["role"], "user")

        big = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 200} for i in range(20)]
        out, meta = prepare_history(big, context_size=400, max_tokens=50)
        self.assertTrue(meta["compressed"])
        self.assertTrue(any(m.get("role") == "system" for m in out))


class SessionFtsTest(unittest.TestCase):
    def test_index_and_search(self):
        from memory import session_fts

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "session_fts.db"
            mem = Path(td) / "memory.json"
            mem.write_text("[]", encoding="utf-8")
            with patch.object(session_fts, "DB_PATH", db), patch.object(session_fts, "MEM_JSON", mem):
                session_fts.index_message("user", "we decided on hermes session search", ts="t1")
                session_fts.index_message("assistant", "ok noted", ts="t2")
                hits = session_fts.search_past_sessions("hermes session", top_k=5)
                self.assertTrue(hits)
                self.assertIn("hermes", hits[0]["content"].lower())


class SkillExperienceTest(unittest.TestCase):
    def test_creates_skill_after_five_successes(self):
        from tools import skill_experience as se

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            with patch("tools.skill_experience.get_workspace", return_value=ws):
                se.reset_episode()
                se.set_task_hint("calc batch")
                for _ in range(5):
                    se.record_tool_call("calc", "42")
                path = se.maybe_create_skill(min_tools=5)
                self.assertIsNotNone(path)
                self.assertTrue(Path(path).is_file())


class PipelineExecTest(unittest.TestCase):
    def test_blocks_dangerous_patterns(self):
        from tools.pipeline_exec import execute_pipeline

        out = execute_pipeline("import os\nos.system('id')")
        self.assertIn("blocked", out.lower())

    def test_allowlisted_calc_via_call(self):
        from tools.pipeline_exec import execute_pipeline

        out = execute_pipeline("result = call('calc', '2+3')")
        self.assertTrue("5" in out or out.startswith("[pipeline]"))


class RouterHermesToolsTest(unittest.TestCase):
    def test_detect_search_past_sessions(self):
        from kernel.router import detect_tool

        tool, args = detect_tool("search past sessions hermes decision", bypass_gate=True)
        self.assertEqual(tool, "search_past_sessions")
        self.assertIn("hermes", args)

    def test_run_tool_uses_hooks(self):
        from kernel.router import run_tool
        from tools.tool_hooks import reset_hooks_for_tests

        reset_hooks_for_tests()
        out = run_tool("calc", "1+1")
        self.assertIn("2", str(out))


class SubagentsAdrTest(unittest.TestCase):
    def test_adr_061_exists(self):
        root = Path(__file__).resolve().parents[2]
        self.assertTrue((root / "docs/adr/ADR-061-subagent-delegation.md").is_file())
        self.assertTrue((root / "docs/adr/ADR-056-tool-call-hooks.md").is_file())
        self.assertFalse((root / "docs/adr/ADR-061-subagent-delegation-deferred.md").is_file())


if __name__ == "__main__":
    unittest.main()
