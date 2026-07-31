"""ADR-091 Signal Soft HTTP relay."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class SignalRelayTest(unittest.TestCase):
    def test_ingest_envelope(self):
        with patch.dict(os.environ, {"KERROS_SIGNAL": "1"}, clear=False):
            from gateway.channels import registry as reg
            from gateway.channels.signal_relay import ingest_signal_payload

            reg._bootstrapped = False
            reg._adapters.clear()
            out = ingest_signal_payload(
                {
                    "envelope": {
                        "source": "+15551212",
                        "dataMessage": {"message": "relay hi"},
                    }
                }
            )
            self.assertTrue(out["ok"], out)
            self.assertEqual(out["enqueued"], 1)
            ad = reg.get_adapter("signal")
            msgs = ad.poll()
            self.assertEqual(msgs[0].text, "relay hi")


if __name__ == "__main__":
    unittest.main()
