"""ADR-069 Discord Soft + live REST (mocked)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class DiscordSoftTest(unittest.TestCase):
    def test_soft_push_poll_send(self):
        with patch.dict(
            os.environ,
            {"KERROS_DISCORD": "1", "KERROS_DISCORD_LIVE": "0"},
            clear=False,
        ):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.discord import DiscordAdapter

            ad = DiscordAdapter()
            st = ad.status()
            self.assertEqual(st["mode"], "soft")
            self.assertTrue(ad.start()["ok"])
            ad.soft_push("hello from soft discord")
            msgs = ad.poll()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].text, "hello from soft discord")
            out = ad.send(OutboundMessage("discord", "chan", "reply"))
            self.assertTrue(out["ok"])
            self.assertEqual(out["mode"], "soft")
            self.assertEqual(ad.status()["soft_outbox"], 1)


class DiscordLiveRestTest(unittest.TestCase):
    def test_live_poll_and_send_mocked(self):
        env = {
            "KERROS_DISCORD": "1",
            "KERROS_DISCORD_LIVE": "1",
            "KERROS_DISCORD_TOKEN": "fake-token",
            "KERROS_DISCORD_CHANNEL": "111",
        }
        with patch.dict(os.environ, env, clear=False):
            from gateway.channels.base import OutboundMessage
            from gateway.channels.discord import DiscordAdapter

            ad = DiscordAdapter()
            self.assertTrue(ad._live())

            poll_payload = [
                {
                    "id": "200",
                    "channel_id": "111",
                    "content": "hi kerr",
                    "author": {"id": "9", "username": "alice", "bot": False},
                },
                {
                    "id": "199",
                    "channel_id": "111",
                    "content": "bot noise",
                    "author": {"id": "1", "username": "bot", "bot": True},
                },
            ]

            class _Resp:
                def __init__(self, body):
                    self._body = body.encode("utf-8")

                def read(self):
                    return self._body

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            def fake_urlopen(req, timeout=20):
                url = req.full_url
                if url.endswith("/users/@me"):
                    return _Resp(json.dumps({"id": "1", "username": "kerrbot"}))
                if "/messages" in url and req.get_method() == "GET":
                    return _Resp(json.dumps(poll_payload))
                if "/messages" in url and req.get_method() == "POST":
                    return _Resp(json.dumps({"id": "300", "content": "reply"}))
                raise AssertionError(url)

            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                started = ad.start()
                self.assertTrue(started["ok"], started)
                self.assertEqual(started["mode"], "live")
                msgs = ad.poll()
                self.assertEqual(len(msgs), 1)
                self.assertEqual(msgs[0].sender, "alice")
                self.assertEqual(msgs[0].text, "hi kerr")
                sent = ad.send(OutboundMessage("discord", "111", "reply"))
                self.assertTrue(sent["ok"], sent)
                self.assertEqual(sent["mode"], "live")


if __name__ == "__main__":
    unittest.main()
