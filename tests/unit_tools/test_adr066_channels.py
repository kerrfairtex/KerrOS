"""ADR-066 channel adapters."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class TelegramSoftTest(unittest.TestCase):
    def test_soft_push_poll_send(self):
        with patch.dict(os.environ, {"KERROS_TELEGRAM": "1", "KERROS_TELEGRAM_LIVE": "0"}, clear=False):
            from gateway.channels.telegram import TelegramAdapter
            from gateway.channels.base import OutboundMessage

            ad = TelegramAdapter()
            self.assertTrue(ad.start()["ok"])
            ad.soft_push("hello from soft tg")
            msgs = ad.poll()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].text, "hello from soft tg")
            out = ad.send(OutboundMessage("telegram", "1", "reply"))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "soft")


class RegistryTest(unittest.TestCase):
    def test_list_and_pump(self):
        with patch.dict(os.environ, {"KERROS_TELEGRAM": "1", "KERROS_GATEWAY": "1"}, clear=False):
            from gateway.channels import registry as reg
            from gateway import webhook as gw

            # reset registry adapters for isolation
            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            started = reg.start_channel("telegram")
            self.assertTrue(started["ok"], started)
            ad = reg.get_adapter("telegram")
            ad.soft_push("pump me")
            pumped = reg.pump_to_webhook_inbox()
            self.assertEqual(pumped["pulled"], 1)
            inbox = gw.inbox_snapshot()
            self.assertTrue(any(m.get("text") == "pump me" for m in inbox))


if __name__ == "__main__":
    unittest.main()
