"""ADR-090 multi-step Soft tool loop."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class ToolLoopTest(unittest.TestCase):
    def test_loop_without_tools(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_TOOLS": "1", "KERROS_CHANNEL_TOOL_STEPS": "2"}, clear=False):
            from gateway.channels.tool_loop import run_tool_loop

            out = run_tool_loop("just chatting with no tool match hopefully xyzzy")
            self.assertTrue(out["ok"])
            self.assertEqual(out["count"], 0)

    def test_tool_loop_reply_soft(self):
        with patch.dict(
            os.environ,
            {
                "KERROS_TELEGRAM": "1",
                "KERROS_CHANNEL_TOOLS": "1",
                "KERROS_CHANNEL_LLM": "0",
            },
            clear=False,
        ):
            from gateway import webhook as gw
            from gateway.channels import registry as reg
            from gateway.channels.tool_loop import tool_loop_reply_once

            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            reg.start_channel("telegram")
            reg.get_adapter("telegram").soft_push("hello loop")
            out = tool_loop_reply_once()
            self.assertEqual(out["pulled"], 1)
            self.assertTrue(out["replies"][0]["outbound"])


if __name__ == "__main__":
    unittest.main()
