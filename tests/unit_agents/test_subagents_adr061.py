"""ADR-061 RAM-aware subagent delegation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from agents.subagents import (
    delegate_tasks,
    parse_delegate_args,
    plan_delegation,
    resolve_max_workers,
)


class SubagentsTest(unittest.TestCase):
    def test_parse_delegate_args(self):
        jobs = parse_delegate_args("knowledge: what is XSS || research: compare WAF")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["agent"], "knowledge")
        self.assertIn("XSS", jobs[0]["task"])

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"KERROS_SUBAGENTS": "0"}, clear=False):
            plan = plan_delegation([{"agent": "knowledge", "task": "x"}])
        self.assertFalse(plan.enabled)
        self.assertIn("disabled", plan.note)

    def test_ram_gate_zero_when_low(self):
        with patch.dict(os.environ, {"KERROS_SUBAGENTS": "1"}, clear=False):
            with patch("agents.subagents.available_ram_mib", return_value=100):
                self.assertEqual(resolve_max_workers({"subagents": {"enabled": True}}), 0)

    def test_ram_gate_two_when_high(self):
        with patch.dict(os.environ, {"KERROS_SUBAGENTS": "1", "KERROS_SUBAGENTS_MAX": "2"}, clear=False):
            with patch("agents.subagents.available_ram_mib", return_value=8000):
                self.assertEqual(resolve_max_workers({"subagents": {"enabled": True, "max_workers": 2}}), 2)

    def test_delegate_runs_parallel_when_enabled(self):
        engine = MagicMock()

        def _fake_run(task, stream=False):
            return f"ok:{task}"

        with patch.dict(os.environ, {"KERROS_SUBAGENTS": "1"}, clear=False):
            with patch("agents.subagents.available_ram_mib", return_value=8000):
                with patch("agents.knowledge.KnowledgeAgent") as KA:
                    with patch("agents.research.ResearchAgent") as RA:
                        KA.return_value.run.side_effect = _fake_run
                        RA.return_value.run.side_effect = _fake_run
                        out = delegate_tasks(
                            [
                                {"agent": "knowledge", "task": "A"},
                                {"agent": "research", "task": "B"},
                            ],
                            engine,
                            cfg={"subagents": {"enabled": True, "max_workers": 2}},
                        )
        self.assertTrue(out["ok"])
        self.assertTrue(out["production_parallel"])
        self.assertEqual(len(out["results"]), 2)

    def test_rejects_disallowed_agent(self):
        engine = MagicMock()
        with patch.dict(os.environ, {"KERROS_SUBAGENTS": "1"}, clear=False):
            with patch("agents.subagents.available_ram_mib", return_value=8000):
                out = delegate_tasks(
                    [{"agent": "security", "task": "scan.example"}],
                    engine,
                    cfg={"subagents": {"enabled": True}},
                )
        self.assertFalse(out["results"][0]["ok"])
        self.assertIn("allowlisted", out["results"][0]["error"])

    def test_detect_delegate_tool(self):
        from kernel.router import detect_tool

        tool, args = detect_tool("delegate knowledge: hello || research: world", bypass_gate=True)
        self.assertEqual(tool, "delegate_task")
        self.assertIn("knowledge", args)

    def test_bind_engine_used_by_router_helper(self):
        from agents.subagents import bind_engine, get_bound_engine

        eng = MagicMock()
        bind_engine(eng)
        self.assertIs(get_bound_engine(), eng)


if __name__ == "__main__":
    unittest.main()
