"""ADR-075 Discord Gateway Soft."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class DiscordGatewaySoftTest(unittest.TestCase):
    def test_soft_dispatch_message_create(self):
        with patch.dict(os.environ, {"KERROS_DISCORD_GATEWAY": "1"}, clear=False):
            from gateway.channels.discord_gateway import reset_discord_gateway, get_discord_gateway

            reset_discord_gateway()
            gw = get_discord_gateway()
            self.assertTrue(gw.start()["ok"])
            gw.soft_dispatch(
                "MESSAGE_CREATE",
                {
                    "content": "hello gateway",
                    "channel_id": "99",
                    "author": {"username": "bob", "bot": False},
                },
            )
            msgs = gw.poll_messages()
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs[0].text, "hello gateway")
            self.assertEqual(msgs[0].sender, "bob")
            gw.stop()
            reset_discord_gateway()

    def test_registry_dispatch_cmd(self):
        with patch.dict(os.environ, {"KERROS_DISCORD_GATEWAY": "1"}, clear=False):
            import json
            from gateway.channels import registry as reg
            from gateway.channels.discord_gateway import reset_discord_gateway

            reset_discord_gateway()
            reg._bootstrapped = False
            reg._adapters.clear()
            from gateway.channels.discord_gateway import get_discord_gateway

            get_discord_gateway().start()
            raw = reg.channels_cmd(
                "gateway-dispatch",
                'MESSAGE_CREATE {"content":"via cmd","channel_id":"1","author":{"username":"a"}}',
            )
            data = json.loads(raw)
            self.assertTrue(data["ok"])
            reset_discord_gateway()


if __name__ == "__main__":
    unittest.main()
