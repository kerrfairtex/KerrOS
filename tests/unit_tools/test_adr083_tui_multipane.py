"""ADR-083 TUI multi-pane status/trace."""

from __future__ import annotations

import unittest


class TuiMultipaneTest(unittest.TestCase):
    def test_trace_and_status(self):
        from cli.tui import KerrTUI

        tui = KerrTUI(reply_fn=lambda s: f"ok:{s}")
        tui.handle("hello")
        self.assertTrue(any("user" in t for t in tui.trace))
        self.assertTrue(any("assistant" in t for t in tui.trace))
        status = tui.status_text()
        self.assertIn("STATUS", status)
        tui.handle("/trace")
        self.assertTrue(any("recent trace" in line for line in tui.lines))


if __name__ == "__main__":
    unittest.main()
