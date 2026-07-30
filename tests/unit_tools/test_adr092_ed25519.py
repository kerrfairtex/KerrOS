"""ADR-092 optional Ed25519 path (Soft default still works)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class Ed25519PathTest(unittest.TestCase):
    def test_soft_still_default(self):
        with patch.dict(os.environ, {"KERROS_DISCORD_INTERACTIONS_SOFT": "1"}, clear=False):
            from gateway.channels.interactions import soft_sign, verify_interaction_request

            body = b'{"type":1}'
            ts = "99"
            sig = soft_sign(ts, body, key="k")
            with patch.dict(os.environ, {"KERROS_DISCORD_PUBLIC_KEY": "k"}, clear=False):
                ok = verify_interaction_request(
                    {"X-Signature-Timestamp": ts, "X-Signature-Ed25519": sig},
                    body,
                )
            self.assertTrue(ok["ok"])

    def test_live_path_without_pynacl_errors_softly(self):
        with patch.dict(os.environ, {"KERROS_DISCORD_INTERACTIONS_SOFT": "0", "KERROS_DISCORD_PUBLIC_KEY": "ab"}, clear=False):
            from gateway.channels.interactions import verify_interaction_request

            res = verify_interaction_request(
                {"X-Signature-Timestamp": "1", "X-Signature-Ed25519": "aa"},
                b"{}",
            )
            self.assertFalse(res["ok"])
            self.assertIn(res.get("mode"), ("ed25519", "ed25519-missing"))


if __name__ == "__main__":
    unittest.main()
