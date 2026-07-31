"""ADR-074 LLM channel bridge."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class LlmBridgeTest(unittest.TestCase):
    def test_soft_fallback_without_llm_flag(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_LLM": "0", "KERROS_TELEGRAM": "1"}, clear=False):
            from gateway.channels import bridge
            from gateway.channels import registry as reg
            from gateway import webhook as gw

            bridge.unbound_channel_engine()
            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            self.assertTrue(reg.start_channel("telegram")["ok"])
            reg.get_adapter("telegram").soft_push("bridge me")
            out = bridge.llm_reply_once()
            self.assertEqual(out["pulled"], 1)
            self.assertEqual(out["replies"][0]["mode"], "soft")
            self.assertIn("bridge me", out["replies"][0]["outbound"])

    def test_llm_path_with_injectable(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_LLM": "1", "KERROS_TELEGRAM": "1"}, clear=False):
            from gateway.channels import bridge
            from gateway.channels import registry as reg
            from gateway import webhook as gw

            bridge.bind_channel_engine(None, generate_fn=lambda p: "llm says hi")
            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            self.assertTrue(reg.start_channel("telegram")["ok"])
            reg.get_adapter("telegram").soft_push("question")
            out = bridge.llm_reply_once()
            self.assertEqual(out["replies"][0]["mode"], "llm")
            self.assertEqual(out["replies"][0]["outbound"], "llm says hi")
            bridge.unbound_channel_engine()


if __name__ == "__main__":
    unittest.main()
