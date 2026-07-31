"""ADR-070 WhatsApp Soft channel."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class WhatsAppSoftTest(unittest.TestCase):
    def test_soft_push_and_webhook(self):
        with patch.dict(os.environ, {"KERROS_WHATSAPP": "1"}, clear=False):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.whatsapp import WhatsAppAdapter

            ad = WhatsAppAdapter()
            self.assertTrue(ad.start()["ok"])
            ad.soft_push("ping")
            self.assertEqual(ad.poll()[0].text, "ping")

            payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {
                                            "from": "15551234567",
                                            "text": {"body": "hello wa"},
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
            enq = ad.soft_push_webhook(payload)
            self.assertEqual(len(enq), 1)
            self.assertEqual(enq[0].text, "hello wa")
            self.assertEqual(enq[0].sender, "15551234567")
            msgs = ad.poll()
            self.assertEqual(len(msgs), 1)
            out = ad.send(OutboundMessage("whatsapp", "15551234567", "ack"))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "soft")

    def test_registry_soft_webhook(self):
        with patch.dict(os.environ, {"KERROS_WHATSAPP": "1"}, clear=False):
            from gateway.channels import registry as reg

            reg._bootstrapped = False
            reg._adapters.clear()
            self.assertTrue(reg.start_channel("whatsapp")["ok"])
            payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "messages": [
                                        {"from": "1", "text": {"body": "via cmd"}}
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
            raw = reg.channels_cmd("soft-webhook", f"whatsapp {json.dumps(payload)}")
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            self.assertEqual(data["enqueued"], 1)


if __name__ == "__main__":
    unittest.main()
