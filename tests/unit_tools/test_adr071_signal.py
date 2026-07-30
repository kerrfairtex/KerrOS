"""ADR-071 Signal Soft channel."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class SignalSoftTest(unittest.TestCase):
    def test_soft_push_poll_send(self):
        with patch.dict(os.environ, {"KERROS_SIGNAL": "1"}, clear=False):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.signal import SignalAdapter

            ad = SignalAdapter()
            self.assertEqual(ad.status()["mode"], "soft")
            self.assertTrue(ad.start()["ok"])
            ad.soft_push("signal ping")
            msgs = ad.poll()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].text, "signal ping")
            out = ad.send(OutboundMessage("signal", "+1555", "ack"))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "soft")
            self.assertEqual(ad.status()["soft_outbox"], 1)


if __name__ == "__main__":
    unittest.main()
