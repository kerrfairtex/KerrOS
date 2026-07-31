"""ADR-078 light TUI shell."""

from __future__ import annotations

import unittest


class TuiShellTest(unittest.TestCase):
    def test_soft_handle_and_clear(self):
        from cli.tui import KerrTUI

        tui = KerrTUI(reply_fn=lambda s: f"echo:{s}")
        self.assertIsNone(tui.handle("hello"))
        self.assertTrue(any("echo:hello" in line for line in tui.lines))
        self.assertEqual(tui.handle("/exit"), "__EXIT__")
        tui.handle("/clear")
        self.assertTrue(any("KerrOS" in line for line in tui.lines))
        self.assertFalse(any("echo:hello" in line for line in tui.lines))


if __name__ == "__main__":
    unittest.main()
