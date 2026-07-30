"""ADR-063 session store."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SessionStoreTest(unittest.TestCase):
    def test_index_search_browse(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db = base / "session_store.db"
            with patch("memory.session_store.BASE", base), patch(
                "memory.session_store.DB_PATH", db
            ), patch("memory.session_fts.index_message", lambda *a, **k: None):
                from memory import session_store as ss

                ss._current_session_id = None
                sid = ss.start_session("test-sess-1")
                ss.index_turn("user", "we decided on session browse feature", session_id=sid)
                ss.index_turn("assistant", "noted the browse plan", session_id=sid)
                hits = ss.search_sessions("browse feature")
                self.assertTrue(hits)
                self.assertEqual(hits[0]["session_id"], sid)
                listed = ss.list_sessions()
                self.assertEqual(listed[0]["session_id"], sid)
                browsed = ss.browse_session(sid)
                self.assertTrue(browsed["ok"])
                self.assertEqual(len(browsed["turns"]), 2)


if __name__ == "__main__":
    unittest.main()
