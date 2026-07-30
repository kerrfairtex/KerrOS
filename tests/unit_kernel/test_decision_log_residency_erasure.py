"""ADR-025: residency stamp + erasure ledger tests (no network)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adapters.audit.decision_log_export import export_decision_log_jsonl
from adapters.audit.erasure_ledger import (
    ErasureLedger,
    evaluate_erasure_request,
    ids_overlap_sealed,
    sealed_id_ranges,
)
from adapters.audit.residency import (
    AuditResidencyConfig,
    maybe_stamp_residency,
    residency_config_from,
)
from adapters.audit.worm_store import WormStore
from kernel.decision_log import DecisionLog


class ResidencyTest(unittest.TestCase):
    def test_defaults_off(self):
        cfg = residency_config_from({})
        self.assertFalse(cfg.enabled)

    def test_stamp_on_export(self):
        out = maybe_stamp_residency(
            {"id": 1, "input_summary": "x"},
            channel="export",
            cfg=AuditResidencyConfig(enabled=True, region="PH-NCR"),
        )
        self.assertEqual(out["residency_region"], "PH-NCR")

    def test_channel_gate(self):
        cfg = AuditResidencyConfig(
            enabled=True, region="EU", stamp_on_siem=False
        )
        siem = maybe_stamp_residency({"a": 1}, channel="siem", cfg=cfg)
        export = maybe_stamp_residency({"a": 1}, channel="export", cfg=cfg)
        self.assertNotIn("residency_region", siem)
        self.assertEqual(export["residency_region"], "EU")

    def test_export_includes_region(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log = DecisionLog(root / "d.db")
            log.record("a", "t", "one", "ok", "", timestamp=1.0)
            dest = root / "out.jsonl"
            privacy_cfg = {
                "audit_residency": {
                    "enabled": True,
                    "region": "IN",
                    "stamp_on_export": True,
                }
            }
            out = export_decision_log_jsonl(
                dest, log=log, skip_rbac=True, privacy_cfg=privacy_cfg
            )
            self.assertTrue(out["ok"])
            line = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(line["residency_region"], "IN")
            self.assertTrue(log.verify_chain().get("ok"))


class ErasureLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "d.db"
        self.worm = self.root / "worm"
        self.erasure_db = self.root / "erasure.db"
        self.log = DecisionLog(self.db)
        for i in range(3):
            self.log.record("a", "t", f"row-{i}", "ok", "", timestamp=float(i + 1))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _cfg(self, **extra):
        base = {
            "audit_erasure": {
                "enabled": True,
                "db_path": str(self.erasure_db),
                "worm_dir": str(self.worm),
            }
        }
        base.update(extra)
        return base

    def test_disabled(self):
        out = evaluate_erasure_request(
            subject_ref="hash:x",
            decision_ids=[1],
            cfg={"audit_erasure": {"enabled": False}},
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])

    def test_recorded_eligible_hot(self):
        out = evaluate_erasure_request(
            subject_ref="hash:subj",
            decision_ids=[1, 2],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["request"]["status"], "eligible_hot_retention")
        self.assertEqual(out["overlap_ids"], [])
        ledger = ErasureLedger(self.erasure_db)
        self.assertEqual(len(ledger.list_recent()), 1)

    def test_blocked_when_sealed(self):
        store = WormStore(self.worm)
        store.seal_from_log(self.log, through_id=2, skip_rbac=True)
        ranges = sealed_id_ranges(store)
        self.assertTrue(ranges)
        self.assertEqual(ids_overlap_sealed([1, 2, 3], ranges), [1, 2])

        out = evaluate_erasure_request(
            subject_ref="hash:subj",
            decision_ids=[1, 2, 3],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["request"]["status"], "blocked_sealed")
        self.assertEqual(out["overlap_ids"], [1, 2])
        # WORM segment still intact / readable.
        self.assertTrue(store.verify_segment(1).get("ok"))
        # Hot chain still verifies (seal does not delete).
        self.assertTrue(self.log.verify_chain().get("ok"))

    def test_ledger_only_without_ids(self):
        out = evaluate_erasure_request(
            subject_ref="hash:only",
            decision_ids=[],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertEqual(out["request"]["status"], "recorded")


if __name__ == "__main__":
    unittest.main()
