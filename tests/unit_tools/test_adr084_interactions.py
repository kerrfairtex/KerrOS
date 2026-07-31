"""ADR-084 Soft Interactions HTTP."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class InteractionsSoftTest(unittest.TestCase):
    def test_soft_sign_and_ping(self):
        with patch.dict(
            os.environ,
            {
                "KERROS_DISCORD_INTERACTIONS_SOFT": "1",
                "KERROS_DISCORD_PUBLIC_KEY": "test-soft-key",
            },
            clear=False,
        ):
            from gateway.channels.interactions import (
                handle_interactions_payload,
                soft_sign,
                verify_interaction_request,
            )

            body = b'{"type":1}'
            ts = "12345"
            sig = soft_sign(ts, body)
            ok = verify_interaction_request(
                {"X-Signature-Timestamp": ts, "X-Signature-Ed25519": sig},
                body,
            )
            self.assertTrue(ok["ok"])
            self.assertEqual(handle_interactions_payload({"type": 1}), {"type": 1})

    def test_application_command(self):
        from gateway.channels.interactions import handle_interactions_payload

        resp = handle_interactions_payload(
            {"type": 2, "channel_id": "1", "data": {"name": "ping"}, "user": {"username": "a"}}
        )
        self.assertEqual(resp.get("type"), 4)
        self.assertIn("Pong", resp.get("data", {}).get("content", ""))


if __name__ == "__main__":
    unittest.main()
