"""ADR-080 Soft stream channel replies."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class StreamReplyTest(unittest.TestCase):
    def test_soft_chunks_and_stream_reply(self):
        with patch.dict(
            os.environ,
            {
                "KERROS_TELEGRAM": "1",
                "KERROS_CHANNEL_LLM": "0",
                "KERROS_CHANNEL_STREAM": "1",
            },
            clear=False,
        ):
            from gateway.channels import bridge
            from gateway.channels import registry as reg
            from gateway import webhook as gw

            bridge.unbound_channel_engine()
            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            reg.start_channel("telegram")
            reg.get_adapter("telegram").soft_push("stream please")
            seen = []
            out = bridge.stream_reply_once(on_chunk=lambda e: seen.append(e.get("type")))
            self.assertEqual(out["pulled"], 1)
            self.assertGreaterEqual(out["replies"][0]["chunks"], 1)
            self.assertIn("chunk", seen)
            self.assertIn("final", seen)


if __name__ == "__main__":
    unittest.main()
