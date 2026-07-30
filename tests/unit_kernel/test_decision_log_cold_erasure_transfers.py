"""ADR-026: sealed-cold erasure review + transfer ledger tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.audit.erasure_ledger import (
    evaluate_erasure_request,
    review_sealed_erasure,
)
from adapters.audit.transfer_ledger import (
    TransferLedger,
    record_transfer_intent,
)
from adapters.audit.worm_store import WormStore
from kernel.decision_log import DecisionLog


class SealedColdReviewTest(unittest.TestCase):
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

    def _cfg(self):
        return {
            "audit_erasure": {
                "enabled": True,
                "db_path": str(self.erasure_db),
                "worm_dir": str(self.worm),
            }
        }

    def test_review_blocked_sealed_keeps_worm(self):
        store = WormStore(self.worm)
        store.seal_from_log(self.log, through_id=2, skip_rbac=True)
        req = evaluate_erasure_request(
            subject_ref="hash:s",
            decision_ids=[1, 2],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertEqual(req["request"]["status"], "blocked_sealed")
        parent_id = int(req["request"]["id"])

        out = review_sealed_erasure(
            parent_id,
            outcome="acknowledged_immutable",
            notes="legal OK to retain",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"])
        self.assertTrue(out["worm_untouched"])
        self.assertTrue(out["worm_verify_ok"])
        self.assertEqual(out["review"]["status"], "review_acknowledged_immutable")
        self.assertTrue(store.verify_segment(1).get("ok"))

    def test_review_rejects_non_blocked(self):
        req = evaluate_erasure_request(
            subject_ref="hash:s",
            decision_ids=[1],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertEqual(req["request"]["status"], "eligible_hot_retention")
        out = review_sealed_erasure(
            int(req["request"]["id"]),
            outcome="legal_hold_retain",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])

    def test_invalid_outcome(self):
        store = WormStore(self.worm)
        store.seal_from_log(self.log, through_id=1, skip_rbac=True)
        req = evaluate_erasure_request(
            subject_ref="hash:s",
            decision_ids=[1],
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        out = review_sealed_erasure(
            int(req["request"]["id"]),
            outcome="delete_worm_please",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])


class TransferLedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "xfer.db"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _cfg(self, **extra):
        base = {
            "audit_transfers": {
                "enabled": True,
                "db_path": str(self.db),
                "default_from_region": "PH-NCR",
            },
            "audit_residency": {"enabled": True, "region": "PH-NCR"},
        }
        base.update(extra)
        return base

    def test_disabled(self):
        out = record_transfer_intent(
            to_region="EU",
            mechanism="scc",
            cfg={"audit_transfers": {"enabled": False}},
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])

    def test_record_cross_border(self):
        out = record_transfer_intent(
            to_region="EU",
            mechanism="scc",
            purpose="support",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"])
        self.assertTrue(out["cross_border"])
        self.assertEqual(out["transfer"]["from_region"], "PH-NCR")
        self.assertEqual(out["transfer"]["to_region"], "EU")
        self.assertEqual(out["transfer"]["mechanism"], "scc")
        ledger = TransferLedger(self.db)
        self.assertEqual(len(ledger.list_recent()), 1)

    def test_same_region(self):
        out = record_transfer_intent(
            to_region="PH-NCR",
            mechanism="internal",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"])
        self.assertFalse(out["cross_border"])

    def test_bad_mechanism(self):
        out = record_transfer_intent(
            to_region="EU",
            mechanism="carrier-pigeon",
            cfg=self._cfg(),
            base=self.root,
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
