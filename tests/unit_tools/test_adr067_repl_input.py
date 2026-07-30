"""ADR-067 REPL input helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ReplInputTest(unittest.TestCase):
    def test_plain_fallback(self):
        with patch.dict(os.environ, {"KERROS_REPL_PT": "0"}, clear=False):
            with patch("builtins.input", return_value="  /help  "):
                from cli.repl_input import prompt_line

                self.assertEqual(prompt_line("> "), "/help")

    def test_slash_commands_include_exit(self):
        from cli.repl_input import SLASH_COMMANDS

        self.assertIn("/exit", SLASH_COMMANDS)
        self.assertIn("/gateway", SLASH_COMMANDS)


if __name__ == "__main__":
    unittest.main()
