"""ADR-024: jurisdiction privacy egress tests (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adapters.audit.decision_log_export import export_decision_log_jsonl
from adapters.audit.privacy import (
    AuditPrivacyConfig,
    maybe_redact_mapping,
    maybe_redact_record,
    privacy_config_from,
    privacy_status,
)
from adapters.audit.siem_forwarder import reset_siem_forwarder
from kernel.decision_log import DecisionLog


class PrivacyConfigTest(unittest.TestCase):
    def test_defaults_disabled(self):
        cfg = privacy_config_from({})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.mode, "hash")

    def test_env_enable(self):
        with patch.dict(
            "os.environ",
            {
                "KERROS_AUDIT_PRIVACY": "1",
                "KERROS_AUDIT_PRIVACY_MODE": "redact",
                "KERROS_AUDIT_PRIVACY_FIELDS": "input_summary,reason",
            },
            clear=False,
        ):
            cfg = privacy_config_from({})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.mode, "redact")
        self.assertEqual(cfg.fields, ["input_summary", "reason"])


class PrivacyTransformTest(unittest.TestCase):
    def test_disabled_passthrough(self):
        out = maybe_redact_mapping(
            {"input_summary": "alice@example.com", "outcome": "ok"},
            channel="export",
            cfg=AuditPrivacyConfig(enabled=False),
        )
        self.assertEqual(out["input_summary"], "alice@example.com")
        self.assertNotIn("privacy", out)

    def test_hash_hides_plaintext(self):
        out = maybe_redact_mapping(
            {"input_summary": "alice@example.com", "outcome": "ok"},
            channel="export",
            cfg=AuditPrivacyConfig(
                enabled=True, mode="hash", salt="s", fields=["input_summary"]
            ),
        )
        self.assertNotEqual(out["input_summary"], "alice@example.com")
        self.assertTrue(str(out["input_summary"]).startswith("hash:"))
        self.assertEqual(out["outcome"], "ok")
        self.assertTrue(out["privacy"]["applied"])

    def test_salt_changes_digest(self):
        a = maybe_redact_mapping(
            {"input_summary": "x"},
            channel="export",
            cfg=AuditPrivacyConfig(
                enabled=True, mode="hash", salt="a", fields=["input_summary"]
            ),
        )
        b = maybe_redact_mapping(
            {"input_summary": "x"},
            channel="export",
            cfg=AuditPrivacyConfig(
                enabled=True, mode="hash", salt="b", fields=["input_summary"]
            ),
        )
        self.assertNotEqual(a["input_summary"], b["input_summary"])

    def test_channel_gate(self):
        cfg = AuditPrivacyConfig(
            enabled=True,
            mode="redact",
            fields=["input_summary"],
            apply_on=["export"],
        )
        export = maybe_redact_mapping(
            {"input_summary": "secret"}, channel="export", cfg=cfg
        )
        siem = maybe_redact_mapping(
            {"input_summary": "secret"}, channel="siem", cfg=cfg
        )
        self.assertEqual(export["input_summary"], "[REDACTED]")
        self.assertEqual(siem["input_summary"], "secret")


class PrivacyExportSiemTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "d.db"
        self.log = DecisionLog(self.db)
        self.log.record(
            "router",
            "verification",
            "email:alice@example.com",
            "ok",
            "note",
            timestamp=1.0,
        )
        reset_siem_forwarder()

    def tearDown(self):
        reset_siem_forwarder()
        self._tmpdir.cleanup()

    def test_export_disabled_preserves_plaintext(self):
        dest = self.root / "out.jsonl"
        out = export_decision_log_jsonl(
            dest,
            log=self.log,
            skip_rbac=True,
            privacy_cfg={"audit_privacy": {"enabled": False}},
        )
        self.assertTrue(out["ok"])
        line = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(line["input_summary"], "email:alice@example.com")

    def test_export_hash_and_chain_still_ok(self):
        dest = self.root / "out.jsonl"
        privacy = {
            "audit_privacy": {
                "enabled": True,
                "mode": "hash",
                "salt": "lab",
                "fields": ["input_summary", "reason", "actor"],
                "apply_on": ["export"],
            }
        }
        out = export_decision_log_jsonl(
            dest, log=self.log, skip_rbac=True, privacy_cfg=privacy
        )
        self.assertTrue(out["ok"])
        line = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("alice@example.com", json.dumps(line))
        self.assertTrue(str(line["input_summary"]).startswith("hash:"))
        # Raw DB chain still verifies.
        self.assertTrue(self.log.verify_chain().get("ok"))

    def test_siem_payload_redacted(self):
        mock = MagicMock()
        mock.forward_record.return_value = True
        privacy = AuditPrivacyConfig(
            enabled=True,
            mode="redact",
            fields=["input_summary"],
            apply_on=["siem"],
        )
        with patch(
            "adapters.audit.privacy.privacy_config_from", return_value=privacy
        ):
            with patch(
                "adapters.audit.siem_forwarder.get_siem_forwarder",
                return_value=mock,
            ):
                log = DecisionLog(self.root / "s.db")
                log.record("a", "t", "pii-subject", "ok", "", timestamp=2.0)
        args = mock.forward_record.call_args[0][0]
        self.assertEqual(args["input_summary"], "[REDACTED]")
        self.assertNotEqual(args.get("input_summary"), "pii-subject")

    def test_privacy_status(self):
        st = privacy_status(
            {"audit_privacy": {"enabled": True, "mode": "hash", "salt": "x"}}
        )
        self.assertTrue(st["enabled"])
        self.assertTrue(st["salt_configured"])


if __name__ == "__main__":
    unittest.main()
