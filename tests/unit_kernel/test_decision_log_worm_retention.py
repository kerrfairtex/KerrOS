"""ADR-019: software-WORM segments + retention policy."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from adapters.audit.retention import apply_retention
from adapters.audit.worm_store import WormStore, WormStoreError
from kernel.decision_log import DecisionLog, GENESIS_HASH
from scripts.apply_retention import main as retain_main
from scripts.seal_decision_log import main as seal_main


class WormStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "decisions.db"
        self.worm_dir = self.root / "worm"
        self.log = DecisionLog(self.db)
        for i in range(1, 4):
            self.log.record("a", "t", f"row-{i}", "ok", "", timestamp=float(i))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_seal_readonly_and_manifest(self):
        store = WormStore(self.worm_dir)
        out = store.seal_from_log(self.log, through_id=2)
        self.assertTrue(out["ok"])
        path = Path(out["path"])
        mode = path.stat().st_mode
        self.assertFalse(mode & stat.S_IWUSR)
        self.assertFalse(out["writable"])
        self.assertEqual(out["tip_hash"], list(self.log.iter_through(2))[-1].entry_hash)
        verify = store.verify_segment(out["segment"])
        self.assertTrue(verify["ok"])

    def test_refuse_rewrite(self):
        store = WormStore(self.worm_dir)
        store.seal_from_log(self.log, through_id=1)
        with self.assertRaises(WormStoreError):
            store.seal_from_log(self.log, through_id=1, segment=1)

    def test_verify_detects_tamper(self):
        store = WormStore(self.worm_dir)
        out = store.seal_from_log(self.log, through_id=2)
        path = Path(out["path"])
        os.chmod(path, 0o644)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        obj = json.loads(lines[0])
        obj["outcome"] = "tampered"
        lines[0] = json.dumps(obj, sort_keys=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(path, 0o444)
        bad = store.verify_segment(out["segment"])
        self.assertFalse(bad["ok"])


class RetentionTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "decisions.db"
        self.worm_dir = self.root / "worm"
        self.log = DecisionLog(self.db)
        # Ages: now=1000; retain_days=1 → cutoff=1000-86400; rows at 1.0 and 2.0 age out
        self.log.record("a", "t", "old-1", "ok", "", timestamp=1.0)
        self.log.record("a", "t", "old-2", "ok", "", timestamp=2.0)
        self.log.record("a", "t", "new", "ok", "", timestamp=900.0)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_disabled_noop(self):
        out = apply_retention(
            self.log,
            cfg={"audit_retention": {"enabled": False, "worm_dir": str(self.worm_dir)}},
            now=1000.0,
        )
        self.assertEqual(out["action"], "noop")
        self.assertEqual(self.log.count(), 3)

    def test_archive_then_hot_chain_ok(self):
        out = apply_retention(
            self.log,
            cfg={
                "audit_retention": {
                    "enabled": True,
                    "retain_days": 1,
                    "action": "archive",
                    "worm_dir": str(self.worm_dir),
                }
            },
            now=500.0 + 86400.0,  # cutoff = 500; rows at 1 and 2 archive; 900 stays
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "archive")
        self.assertEqual(out["through_id"], 2)
        # hot: "new" + retention_apply audit row
        self.assertGreaterEqual(self.log.count(), 1)
        self.assertTrue(self.log.verify_chain()["ok"])
        remaining = list(self.log.iter_from(0))
        # first remaining should be "new" (id 3) whose prev_hash is tip of sealed
        new_row = next(r for r in remaining if r.input_summary == "new")
        sealed_tip = out["segment"]["tip_hash"]
        self.assertEqual(new_row.prev_hash, sealed_tip)
        store = WormStore(self.worm_dir)
        self.assertTrue(store.verify_segment(out["segment"]["segment"])["ok"])

    def test_purge_refused_without_flag(self):
        out = apply_retention(
            self.log,
            cfg={
                "audit_retention": {
                    "enabled": True,
                    "retain_days": 1,
                    "action": "purge",
                    "allow_purge": False,
                    "worm_dir": str(self.worm_dir),
                }
            },
            now=500.0 + 86400.0,
        )
        self.assertFalse(out["ok"])
        self.assertIn("allow_purge", out["error"])

    def test_delete_through_requires_flag(self):
        with self.assertRaises(RuntimeError):
            self.log.delete_through(1)

    def test_verify_chain_anchors_after_prefix_delete(self):
        # Manual seal + delete to simulate archive without retention_apply noise
        store = WormStore(self.worm_dir)
        sealed = store.seal_from_log(self.log, through_id=2)
        self.log.delete_through(2, _retention=True)
        result = self.log.verify_chain()
        self.assertTrue(result["ok"])
        first = next(self.log.iter_from(0))
        self.assertEqual(first.prev_hash, sealed["tip_hash"])
        self.assertNotEqual(first.prev_hash, GENESIS_HASH)

    def test_cli_seal_and_retain(self):
        rc = seal_main(
            [
                "--db",
                str(self.db),
                "--worm-dir",
                str(self.worm_dir),
                "--through-id",
                "1",
            ]
        )
        self.assertEqual(rc, 0)
        rc = retain_main(
            [
                "--db",
                str(self.db),
                "--enable",
                "--retain-days",
                "1",
                "--action",
                "archive",
                "--worm-dir",
                str(self.worm_dir),
                "--now",
                str(500.0 + 86400.0),
            ]
        )
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
