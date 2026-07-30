"""Smoke tests for cli.ui brand chrome."""

from __future__ import annotations

import unittest
from unittest.mock import patch


class CliUiTest(unittest.TestCase):
    def test_angel_logo_keeps_brand(self):
        from cli.ui import ANGEL_LOGO, WORDMARK

        self.assertIn("⚔", ANGEL_LOGO)
        self.assertIn("██", WORDMARK)
        self.assertIn("╲", ANGEL_LOGO)

    def test_welcome_banner_prints(self):
        from cli.ui import print_welcome_banner

        with patch("builtins.print") as p:
            print_welcome_banner(
                mode="offline",
                workspace="/tmp/ws",
                session_id="abc123",
                phase="ready",
                model_hint="local",
            )
        self.assertTrue(p.called)
        joined = " ".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertIn("KerrOS", joined)
        self.assertIn("/help", joined)


if __name__ == "__main__":
    unittest.main()
