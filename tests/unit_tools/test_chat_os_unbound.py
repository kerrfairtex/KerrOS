"""Regression: nested import os in main() shadows module os (Termux crash)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


class ChatOsImportTest(unittest.TestCase):
    def test_main_does_not_reimport_os(self):
        path = Path(__file__).resolve().parents[2] / "cli" / "chat.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            self.assertNotEqual(
                                alias.name,
                                "os",
                                "nested 'import os' in main() causes UnboundLocalError "
                                "before the import runs (Termux offline chat crash)",
                            )


if __name__ == "__main__":
    unittest.main()
