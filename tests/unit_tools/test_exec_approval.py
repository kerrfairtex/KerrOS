"""ADR-062 exec approval patterns."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from tools.exec_approval import check_exec_approval, detect_dangerous_command


class ExecApprovalTest(unittest.TestCase):
    def test_detects_rm_rf(self):
        self.assertIsNotNone(detect_dangerous_command("rm -rf /tmp/x"))

    def test_blocks_by_default(self):
        with patch.dict(os.environ, {"KERROS_EXEC_GUARD": "1"}, clear=False):
            # clear approve
            os.environ.pop("KERROS_EXEC_APPROVE", None)
            ok, reason = check_exec_approval("bash", "rm -rf /")
            self.assertFalse(ok)
            self.assertIn("dangerous", reason)

    def test_non_shell_passthrough(self):
        ok, _ = check_exec_approval("calc", "1+1")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
