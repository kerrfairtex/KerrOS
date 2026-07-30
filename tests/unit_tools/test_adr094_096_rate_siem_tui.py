"""ADR-094/095/096 SIEM push Soft, rate limit, TUI channel."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class RateLimitTest(unittest.TestCase):
    def test_rate_limit_blocks(self):
        with patch.dict(os.environ, {"KERROS_CHANNEL_RATE": "2/60"}, clear=False):
            from gateway.channels.rate_limit import allow, reset_limits

            reset_limits()
            self.assertTrue(allow("tg", "1", "a")["allowed"])
            self.assertTrue(allow("tg", "1", "a")["allowed"])
            self.assertFalse(allow("tg", "1", "a")["allowed"])


class SiemPushTest(unittest.TestCase):
    def test_soft_plan(self):
        with patch.dict(os.environ, {"KERROS_SIEM_PUSH": "0"}, clear=False):
            from gateway.channels.siem_push import push_trace

            out = push_trace()
            self.assertTrue(out["ok"])
            self.assertTrue(out.get("soft"))

    def test_live_mocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            tpath = base / "data" / "channel_trace.jsonl"
            env = {
                "KERROS_SIEM_PUSH": "1",
                "KERROS_SIEM_URL": "http://127.0.0.1:9/siem",
            }
            with patch.dict(os.environ, env, clear=False), patch(
                "gateway.channels.trace.BASE", base
            ), patch("gateway.channels.trace.TRACE_PATH", tpath):
                from gateway.channels import siem_push as sp
                from gateway.channels import trace as tr

                tr.clear_trace()
                tr.append_trace("x", {})

                class _Resp:
                    def read(self):
                        return b'{"ok":true}'

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                with patch("urllib.request.urlopen", return_value=_Resp()):
                    out = sp.push_trace(format="json")
                self.assertTrue(out["ok"])
                self.assertFalse(out.get("soft"))


class TuiChannelTest(unittest.TestCase):
    def test_channel_command(self):
        from cli.tui import KerrTUI

        tui = KerrTUI()
        with patch(
            "gateway.channels.registry.channels_cmd",
            return_value=json.dumps({"ok": True, "pulled": 0}),
        ):
            tui.handle("/channel soft-reply")
        self.assertTrue(any("channel soft-reply" in line for line in tui.lines))


if __name__ == "__main__":
    unittest.main()
