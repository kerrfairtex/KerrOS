"""ADR-076 WhatsApp/Signal live Soft paths."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class WhatsAppLiveSoftTest(unittest.TestCase):
    def test_live_send_mocked(self):
        env = {
            "KERROS_WHATSAPP": "1",
            "KERROS_WHATSAPP_LIVE": "1",
            "KERROS_WHATSAPP_TOKEN": "tok",
            "KERROS_WHATSAPP_PHONE_ID": "phone1",
        }
        with patch.dict(os.environ, env, clear=False):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.whatsapp import WhatsAppAdapter

            ad = WhatsAppAdapter()
            self.assertTrue(ad._live())

            class _Resp:
                def read(self):
                    return json.dumps({"messages": [{"id": "wamid.1"}]}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            with patch("urllib.request.urlopen", return_value=_Resp()):
                out = ad.send(OutboundMessage("whatsapp", "15551234567", "hi"))
                self.assertTrue(out["ok"], out)
                self.assertEqual(out["mode"], "live")


class SignalLiveSoftTest(unittest.TestCase):
    def test_live_without_cli_stays_soft_send_queue(self):
        with patch.dict(
            os.environ,
            {"KERROS_SIGNAL": "1", "KERROS_SIGNAL_LIVE": "1", "KERROS_SIGNAL_CLI": "no-such-cli-bin"},
            clear=False,
        ):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.signal import SignalAdapter

            ad = SignalAdapter()
            self.assertFalse(ad._live())
            self.assertTrue(ad.start()["ok"])
            out = ad.send(OutboundMessage("signal", "+1", "x"))
            self.assertEqual(out["mode"], "soft")


if __name__ == "__main__":
    unittest.main()
