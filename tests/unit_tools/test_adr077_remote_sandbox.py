"""ADR-077 remote sandbox Soft backend."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch


class RemoteSandboxTest(unittest.TestCase):
    def test_soft_plan(self):
        with patch.dict(os.environ, {"KERROS_BG_BACKEND": "remote", "KERROS_REMOTE_SANDBOX": "0"}, clear=False):
            from tools.process_backends import get_backend

            b = get_backend()
            self.assertEqual(b.name, "remote")
            h = b.spawn("echo hi")
            self.assertEqual(h.status, "exited")
            self.assertIn("remote soft", h.output)

    def test_live_http_mocked(self):
        env = {
            "KERROS_BG_BACKEND": "remote",
            "KERROS_REMOTE_SANDBOX": "1",
            "KERROS_REMOTE_SANDBOX_URL": "http://127.0.0.1:9/exec",
        }
        with patch.dict(os.environ, env, clear=False):
            from tools.process_backends import get_backend

            class _Resp:
                def read(self):
                    return json.dumps({"ok": True, "output": "done\n", "exit_code": 0}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            with patch("urllib.request.urlopen", return_value=_Resp()):
                h = get_backend().spawn("uname")
                self.assertEqual(h.status, "exited")
                self.assertEqual(h.returncode, 0)
                self.assertIn("done", h.output)
                self.assertFalse(h.meta.get("soft"))


if __name__ == "__main__":
    unittest.main()
