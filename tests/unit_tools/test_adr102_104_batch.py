"""ADR-102…104 stream edits, secrets vault, health probes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class StreamEditTest(unittest.TestCase):
    def test_soft_stream_edit(self):
        with patch.dict(
            os.environ,
            {
                "KERROS_TELEGRAM": "1",
                "KERROS_CHANNEL_LLM": "0",
                "KERROS_CHANNEL_STREAM": "1",
            },
            clear=False,
        ):
            from gateway import webhook as gw
            from gateway.channels import registry as reg
            from gateway.channels.stream_edit import stream_edit_reply_once

            reg._bootstrapped = False
            reg._adapters.clear()
            gw.clear_inbox()
            reg.start_channel("telegram")
            reg.get_adapter("telegram").soft_push("edit stream please")
            edits = []
            out = stream_edit_reply_once(on_edit=lambda e: edits.append(e))
            self.assertEqual(out["pulled"], 1)
            self.assertGreaterEqual(out["replies"][0]["edits"], 1)
            self.assertTrue(edits)
            ad = reg.get_adapter("telegram")
            soft_edits = getattr(ad, "_soft_edits", [])
            self.assertGreaterEqual(len(soft_edits) + len(edits), 1)


class SecretsVaultTest(unittest.TestCase):
    def test_set_list_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            vault = base / "data" / "channel_secrets.json"
            with patch("gateway.channels.secrets.BASE", base), patch(
                "gateway.channels.secrets.VAULT", vault
            ):
                from gateway.channels import secrets as sec

                self.assertTrue(sec.set_secret("FOO_TOKEN", "abc123")["ok"])
                listed = sec.list_secrets()
                self.assertIn("FOO_TOKEN", listed["names"])
                self.assertEqual(sec.get_secret("FOO_TOKEN"), "abc123")
                # apply into env when missing
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("FOO_TOKEN", None)
                    applied = sec.apply_vault_to_environ(keys=["FOO_TOKEN"])
                    self.assertIn("FOO_TOKEN", applied["applied"])


class HealthProbeTest(unittest.TestCase):
    def test_probe(self):
        from gateway.channels.health import probe_channels

        out = probe_channels()
        self.assertTrue(out["ok"])
        self.assertIn("channels", out)
        self.assertIn("latency_ms", out)


if __name__ == "__main__":
    unittest.main()
