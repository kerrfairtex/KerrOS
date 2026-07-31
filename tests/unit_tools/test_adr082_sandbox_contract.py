"""ADR-082 remote sandbox image/mount contract."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class SandboxContractTest(unittest.TestCase):
    def test_soft_plan_includes_contract(self):
        env = {
            "KERROS_BG_BACKEND": "remote",
            "KERROS_REMOTE_SANDBOX": "0",
            "KERROS_REMOTE_SANDBOX_IMAGE": "kerros/sandbox:1",
            "KERROS_REMOTE_SANDBOX_MOUNTS": "/workspace:/work:ro,/tmp:/tmp:rw",
        }
        with patch.dict(os.environ, env, clear=False):
            from tools.process_backends import get_backend

            h = get_backend().spawn("echo hi")
            self.assertTrue(h.meta.get("soft"))
            contract = h.meta.get("contract") or {}
            self.assertEqual(contract.get("image"), "kerros/sandbox:1")
            self.assertEqual(len(contract.get("mounts") or []), 2)
            self.assertIn("image=kerros/sandbox:1", h.output)


if __name__ == "__main__":
    unittest.main()
