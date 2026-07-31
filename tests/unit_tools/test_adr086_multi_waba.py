"""ADR-086 WhatsApp multi-WABA Soft."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class MultiWabaTest(unittest.TestCase):
    def test_webhook_sets_active_phone(self):
        env = {
            "KERROS_WHATSAPP": "1",
            "KERROS_WHATSAPP_WABAS": json.dumps(
                {
                    "111": {"token": "tokA", "label": "sales"},
                    "222": {"token": "tokB", "label": "support"},
                }
            ),
        }
        with patch.dict(os.environ, env, clear=False):
            from gateway.channels.whatsapp import WhatsAppAdapter, load_waba_map

            self.assertEqual(len(load_waba_map()), 2)
            ad = WhatsAppAdapter()
            st = ad.status()
            self.assertEqual(len(st["wabas"]), 2)
            payload = {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": "222"},
                                    "messages": [
                                        {"from": "1555", "text": {"body": "hi support"}}
                                    ],
                                }
                            }
                        ]
                    }
                ]
            }
            msgs = ad.soft_push_webhook(payload)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].raw.get("phone_number_id"), "222")
            self.assertEqual(msgs[0].raw.get("waba_label"), "support")
            self.assertEqual(ad._active_phone_id, "222")


if __name__ == "__main__":
    unittest.main()
