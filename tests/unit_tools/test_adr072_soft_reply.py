"""ADR-072 Soft channel reply loop."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SoftReplyTest(unittest.TestCase):
    def test_soft_reply_indexes_and_acks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db = base / "session_store.db"
            env = {
                "KERROS_TELEGRAM": "1",
                "KERROS_TELEGRAM_LIVE": "0",
                "KERROS_GATEWAY": "1",
            }
            with patch.dict(os.environ, env, clear=False), patch(
                "memory.session_store.BASE", base
            ), patch("memory.session_store.DB_PATH", db), patch(
                "memory.session_fts.index_message", lambda *a, **k: None
            ):
                from gateway import webhook as gw
                from gateway.channels import registry as reg
                from memory.session_store import list_sessions

                reg._bootstrapped = False
                reg._adapters.clear()
                gw.clear_inbox()
                self.assertTrue(reg.start_channel("telegram")["ok"])
                ad = reg.get_adapter("telegram")
                ad.soft_push("need soft ack")
                out = reg.soft_reply_once()
                self.assertEqual(out["pulled"], 1)
                self.assertEqual(len(out["replies"]), 1)
                self.assertIn("need soft ack", out["replies"][0]["outbound"])
                inbox = gw.inbox_snapshot()
                self.assertTrue(any(m.get("text") == "need soft ack" for m in inbox))
                # Soft outbox got the ack
                self.assertEqual(ad.status()["soft_outbox"], 1)
                sessions = list_sessions()
                self.assertTrue(sessions)


if __name__ == "__main__":
    unittest.main()
