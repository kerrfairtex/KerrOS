"""ADR-073 REPL multiline continuation."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class ReplMultilineTest(unittest.TestCase):
    def test_backslash_continuation(self):
        with patch.dict(
            os.environ, {"KERROS_REPL_PT": "0", "KERROS_REPL_MULTILINE": "1"}, clear=False
        ):
            from cli.repl_input import join_continued_lines, prompt_line

            self.assertEqual(join_continued_lines(["a", "b"]), "a\nb")
            with patch("builtins.input", side_effect=["line one\\", "line two"]):
                self.assertEqual(prompt_line("> "), "line one\nline two")

    def test_multiline_can_disable(self):
        with patch.dict(
            os.environ, {"KERROS_REPL_PT": "0", "KERROS_REPL_MULTILINE": "0"}, clear=False
        ):
            from cli.repl_input import prompt_line

            with patch("builtins.input", return_value="keep\\"):
                # trailing slash kept when multiline off (after strip of whole)
                self.assertEqual(prompt_line("> "), "keep\\")


if __name__ == "__main__":
    unittest.main()
