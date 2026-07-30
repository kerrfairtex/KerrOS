"""ADR-087 persisted channel/TUI trace."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TraceStoreTest(unittest.TestCase):
    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            path = base / "data" / "channel_trace.jsonl"
            with patch("gateway.channels.trace.BASE", base), patch(
                "gateway.channels.trace.TRACE_PATH", path
            ):
                from gateway.channels import trace as tr

                tr.clear_trace()
                tr.append_trace("test", {"x": 1})
                rows = tr.read_trace(limit=5)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["kind"], "test")
                fmt = tr.format_trace()
                self.assertIn("test", fmt)


if __name__ == "__main__":
    unittest.main()
