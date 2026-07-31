"""ADR-097…101 SIEM queue, shared rate, bridge auth, JSON plans, TUI ops."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class SiemQueueTest(unittest.TestCase):
    def test_enqueue_and_flush_soft(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            q = base / "data" / "siem_queue.jsonl"
            with patch("gateway.channels.siem_queue.BASE", base), patch(
                "gateway.channels.siem_queue.QUEUE_PATH", q
            ):
                from gateway.channels import siem_queue as sq

                sq.enqueue_failed(
                    format="json",
                    body=b'{"ok":true}',
                    content_type="application/json",
                    error="boom",
                )
                st = sq.queue_status()
                self.assertEqual(st["pending"], 1)
                with patch.dict(os.environ, {"KERROS_SIEM_PUSH": "0"}, clear=False):
                    out = sq.flush_siem_queue()
                self.assertTrue(out.get("soft"))
                self.assertEqual(out["pending"], 1)


class SharedRateTest(unittest.TestCase):
    def test_shared_file_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = base / "data" / "channel_rate.json"
            env = {"KERROS_CHANNEL_RATE": "2/60", "KERROS_CHANNEL_RATE_SHARED": "1"}
            with patch.dict(os.environ, env, clear=False), patch(
                "gateway.channels.rate_limit.BASE", base
            ), patch("gateway.channels.rate_limit.STORE", store):
                from gateway.channels.rate_limit import allow, reset_limits

                reset_limits()
                self.assertTrue(allow("tg", "1", "a")["allowed"])
                self.assertTrue(allow("tg", "1", "a")["allowed"])
                self.assertFalse(allow("tg", "1", "a")["allowed"])
                self.assertTrue(store.exists())


class BridgeAuthTest(unittest.TestCase):
    def test_sign_verify(self):
        env = {
            "KERROS_BRIDGE_AUTH": "1",
            "KERROS_BRIDGE_SECRETS": json.dumps({"sig1": "s3cret"}),
        }
        with patch.dict(os.environ, env, clear=False):
            from gateway.channels.bridge_auth import sign_bridge, verify_bridge_request

            body = b'{"text":"hi"}'
            ts = str(int(time.time()))
            sig = sign_bridge("sig1", ts, body, "s3cret")
            ok = verify_bridge_request(
                {
                    "X-Kerros-Bridge-Id": "sig1",
                    "X-Kerros-Bridge-Ts": ts,
                    "X-Kerros-Bridge-Sign": sig,
                },
                body,
            )
            self.assertTrue(ok["ok"], ok)


class JsonPlanTest(unittest.TestCase):
    def test_parse_and_run(self):
        from gateway.channels.structured_plan import parse_structured_plan, run_structured_plan

        steps = parse_structured_plan(
            json.dumps({"steps": [{"action": "reply", "text": "a"}, {"action": "reply", "text": "b"}]})
        )
        self.assertEqual(len(steps), 2)
        with patch.dict(os.environ, {"KERROS_CHANNEL_LLM": "0"}, clear=False):
            out = run_structured_plan(json.dumps({"steps": [{"action": "reply", "text": "hello"}]}))
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["count"], 1)


class TuiOpsPaneTest(unittest.TestCase):
    def test_ops_recording(self):
        from cli.tui import KerrTUI

        tui = KerrTUI()
        with patch(
            "gateway.channels.registry.channels_cmd",
            return_value=json.dumps({"ok": True, "pulled": 0}),
        ):
            tui.handle("/channel soft-reply")
        self.assertTrue(any("soft-reply" in x for x in tui.channel_ops))
        self.assertIn("CHANNEL OPS", tui.ops_text())


if __name__ == "__main__":
    unittest.main()
