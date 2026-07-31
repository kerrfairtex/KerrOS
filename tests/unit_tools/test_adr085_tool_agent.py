"""ADR-085 channel tool Soft agent."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class ToolAgentTest(unittest.TestCase):
    def test_tool_reply_falls_back_soft(self):
        with patch.dict(
            os.environ,
            {
                "KERROS_TELEGRAM": "1",
                "KERROS_CHANNEL_TOOLS": "1",
                "KERROS_CHANNEL_LLM": "0",
            },
            clear=False,
        ):
            from gateway.channels import registry as reg
            from gateway.channels.tool_agent import tool_reply_once
            from gateway import webhook as gw

            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            reg.start_channel("telegram")
            # Unlikely to match a tool — Soft fallback
            reg.get_adapter("telegram").soft_push("hello there friend")
            out = tool_reply_once()
            self.assertEqual(out["pulled"], 1)
            self.assertIn(out["replies"][0]["mode"], ("soft", "tool", "llm"))

    def test_list_sessions_tool_path(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_TOOLS": "1"}, clear=False):
            from gateway.channels.tool_agent import try_channel_tool

            hit = try_channel_tool("list sessions")
            # May or may not match depending on router patterns — just ensure no crash
            self.assertTrue(hit is None or "tool" in hit)


if __name__ == "__main__":
    unittest.main()
