"""ADR-093 Soft planner channel agent."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class PlannerTest(unittest.TestCase):
    def test_split_and_plan_reply(self):
        from gateway.channels.planner_agent import run_plan, split_plan

        self.assertGreaterEqual(len(split_plan("a then b then c")), 3)
        with patch.dict(os.environ, {"KERROS_CHANNEL_LLM": "0", "KERROS_CHANNEL_TOOLS": "1"}, clear=False):
            out = run_plan("say hi then say bye")
            self.assertTrue(out["ok"])
            self.assertGreaterEqual(out["count"], 2)

        with patch.dict(
            os.environ,
            {"KERROS_TELEGRAM": "1", "KERROS_CHANNEL_PLANNER": "1", "KERROS_CHANNEL_LLM": "0"},
            clear=False,
        ):
            from gateway import webhook as gw
            from gateway.channels import registry as reg
            from gateway.channels.planner_agent import planner_reply_once

            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            reg.start_channel("telegram")
            reg.get_adapter("telegram").soft_push("one then two")
            reply = planner_reply_once()
            self.assertEqual(reply["pulled"], 1)
            self.assertEqual(reply["replies"][0]["mode"], "planner")


if __name__ == "__main__":
    unittest.main()
