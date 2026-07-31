"""ADR-081 Discord slash Soft."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class SlashSoftTest(unittest.TestCase):
    def test_ping_and_interaction(self):
        with patch.dict(os.environ, {"KERROS_DISCORD_GATEWAY": "1"}, clear=False):
            from gateway.channels.slash import handle_slash_command, soft_interaction_create
            from gateway.channels.discord_gateway import reset_discord_gateway, get_discord_gateway

            ping = handle_slash_command("ping")
            self.assertTrue(ping["ok"])
            self.assertIn("Pong", ping["content"])

            reset_discord_gateway()
            gw = get_discord_gateway()
            gw.start()
            res = gw.soft_dispatch(
                "INTERACTION_CREATE",
                {
                    "type": 2,
                    "channel_id": "42",
                    "data": {"name": "status"},
                    "user": {"username": "op"},
                },
            )
            self.assertTrue(res.get("ok"))
            self.assertIn("slash", res)
            reset_discord_gateway()

    def test_registry_slash_cmd(self):
        from gateway.channels import registry as reg

        raw = reg.channels_cmd("slash", "help")
        data = json.loads(raw)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
