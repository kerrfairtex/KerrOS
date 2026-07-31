"""ADR-079 per-channel session routing."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ChannelRoutingTest(unittest.TestCase):
    def test_stable_session_ids(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_ROUTING": "1"}, clear=False):
            from gateway.channels.routing import clear_route_cache, session_id_for

            clear_route_cache()
            a = session_id_for("telegram", "111", "alice")
            b = session_id_for("telegram", "111", "alice")
            c = session_id_for("telegram", "222", "alice")
            self.assertEqual(a, b)
            self.assertNotEqual(a, c)
            self.assertTrue(a.startswith("ch-telegram-"))

    def test_soft_reply_uses_routed_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db = base / "session_store.db"
            env = {
                "KERROS_TELEGRAM": "1",
                "KERROS_TELEGRAM_LIVE": "0",
                "KERROS_CHANNEL_ROUTING": "1",
            }
            with patch.dict(os.environ, env, clear=False), patch(
                "memory.session_store.BASE", base
            ), patch("memory.session_store.DB_PATH", db), patch(
                "memory.session_fts.index_message", lambda *a, **k: None
            ):
                from gateway import webhook as gw
                from gateway.channels import registry as reg
                from gateway.channels.routing import clear_route_cache
                from memory.session_store import list_sessions

                clear_route_cache()
                reg._bootstrapped = False
                reg._adapters.clear()
                gw.clear_inbox()
                reg.start_channel("telegram")
                reg.get_adapter("telegram").soft_push("routed", sender="bob", chat_id="9")
                out = reg.soft_reply_once()
                self.assertEqual(out["pulled"], 1)
                self.assertTrue(out["replies"][0]["session_id"].startswith("ch-"))
                self.assertTrue(list_sessions())


if __name__ == "__main__":
    unittest.main()
