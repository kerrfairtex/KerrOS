"""ADR-068 session resume into REPL memory."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SessionResumeTest(unittest.TestCase):
    def test_resume_loads_short_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db = base / "session_store.db"
            with patch("memory.session_store.BASE", base), patch(
                "memory.session_store.DB_PATH", db
            ), patch("memory.session_fts.index_message", lambda *a, **k: None):
                from memory import manager as mm
                from memory import session_store as ss

                ss._current_session_id = None
                mm._short = []
                sid = ss.start_session("resume-sess-1")
                ss.index_turn("user", "remember the deploy checklist", session_id=sid)
                ss.index_turn("assistant", "checklist noted", session_id=sid)

                # New empty live session
                ss.start_session("other-live")
                mm._short = [{"role": "user", "content": "unrelated", "time": "x"}]

                out = mm.resume_session(sid)
                self.assertTrue(out["ok"])
                self.assertEqual(out["session_id"], sid)
                self.assertEqual(out["loaded"], 2)
                self.assertEqual(mm.get_recent(10)[0]["content"], "remember the deploy checklist")
                self.assertEqual(ss.get_current_session_id(), sid)

                latest = mm.resume_session("latest")
                self.assertTrue(latest["ok"])
                self.assertEqual(latest["session_id"], sid)

                picker = mm.format_resume_picker()
                self.assertIn(sid, picker)


if __name__ == "__main__":
    unittest.main()
