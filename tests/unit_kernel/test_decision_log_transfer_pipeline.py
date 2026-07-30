"""ADR-027: automated transfer pipeline tests (no network for local_copy)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adapters.audit.transfer_ledger import record_transfer_intent
from adapters.audit.transfer_pipeline import execute_transfer, pipeline_config_from
from adapters.audit.worm_store import WormStore
from kernel.decision_log import DecisionLog


class TransferPipelineTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "d.db"
        self.worm = self.root / "worm"
        self.xfer_db = self.root / "xfer.db"
        self.outbox = self.root / "outbox"
        self.log = DecisionLog(self.db)
        for i in range(2):
            self.log.record("a", "t", f"row-{i}", "ok", "", timestamp=float(i + 1))
        WormStore(self.worm).seal_from_log(self.log, through_id=2, skip_rbac=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _cfg(self, **extra):
        base = {
            "audit_residency": {"enabled": True, "region": "PH-NCR"},
            "audit_transfers": {
                "enabled": True,
                "db_path": str(self.xfer_db),
                "default_from_region": "PH-NCR",
                "execute_enabled": True,
                "backend": "local_copy",
                "dest_dir": str(self.outbox),
                "sources": ["sealed_segments"],
                "worm_dir": str(self.worm),
            },
            "audit_retention": {"worm_dir": str(self.worm)},
        }
        # shallow merge for audit_transfers overrides
        if "audit_transfers" in extra:
            base["audit_transfers"].update(extra.pop("audit_transfers"))
        base.update(extra)
        return base

    def test_execute_disabled(self):
        cfg = self._cfg()
        cfg["audit_transfers"]["execute_enabled"] = False
        intent = record_transfer_intent(
            to_region="EU", mechanism="scc", cfg=cfg, base=self.root, skip_rbac=True
        )
        out = execute_transfer(
            int(intent["transfer"]["id"]),
            cfg=cfg,
            base=self.root,
            skip_rbac=True,
        )
        self.assertFalse(out["ok"])
        self.assertIn("execute disabled", out["error"])

    def test_local_copy_executes_and_leaves_worm(self):
        cfg = self._cfg()
        intent = record_transfer_intent(
            to_region="EU", mechanism="scc", cfg=cfg, base=self.root, skip_rbac=True
        )
        tid = int(intent["transfer"]["id"])
        out = execute_transfer(tid, cfg=cfg, base=self.root, skip_rbac=True)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["worm_untouched"])
        self.assertEqual(out["transfer"]["status"], "executed")
        self.assertTrue(any(Path(p).name.endswith(".jsonl") for p in out["artifacts"]))
        man = Path(out["dest_dir"]) / "transfer_manifest.json"
        self.assertTrue(man.is_file())
        data = json.loads(man.read_text(encoding="utf-8"))
        self.assertEqual(data["to_region"], "EU")
        # Source still verifies.
        self.assertTrue(WormStore(self.worm).verify_segment(1).get("ok"))

    def test_idempotent_second_execute(self):
        cfg = self._cfg()
        intent = record_transfer_intent(
            to_region="EU", mechanism="adequacy", cfg=cfg, base=self.root, skip_rbac=True
        )
        tid = int(intent["transfer"]["id"])
        self.assertTrue(
            execute_transfer(tid, cfg=cfg, base=self.root, skip_rbac=True)["ok"]
        )
        again = execute_transfer(tid, cfg=cfg, base=self.root, skip_rbac=True)
        self.assertFalse(again["ok"])
        self.assertIn("already executed", again["error"])

    def test_http_put_mocked(self):
        cfg = self._cfg(
            audit_transfers={
                "backend": "http_put",
                "http_url": "http://127.0.0.1:9/put",
                "sources": ["sealed_segments"],
            }
        )
        intent = record_transfer_intent(
            to_region="EU", mechanism="scc", cfg=cfg, base=self.root, skip_rbac=True
        )
        with patch("adapters.audit.transfer_pipeline._http_put") as put:
            put.return_value = None
            out = execute_transfer(
                int(intent["transfer"]["id"]),
                cfg=cfg,
                base=self.root,
                skip_rbac=True,
            )
        self.assertTrue(out["ok"], out)
        put.assert_called_once()

    def test_export_source(self):
        cfg = self._cfg(
            audit_transfers={"sources": ["export_jsonl", "sealed_segments"]}
        )
        intent = record_transfer_intent(
            to_region="IN", mechanism="consent", cfg=cfg, base=self.root, skip_rbac=True
        )
        out = execute_transfer(
            int(intent["transfer"]["id"]),
            cfg=cfg,
            base=self.root,
            decision_log_db=self.db,
            skip_rbac=True,
        )
        self.assertTrue(out["ok"], out)
        names = [Path(p).name for p in out["artifacts"]]
        self.assertIn("decision_log_export.jsonl", names)

    def test_pipeline_config_env(self):
        with patch.dict(
            "os.environ",
            {"KERROS_AUDIT_TRANSFER_EXECUTE": "1", "KERROS_AUDIT_TRANSFER_BACKEND": "http_put"},
        ):
            p = pipeline_config_from(
                {
                    "audit_transfers": {
                        "enabled": True,
                        "db_path": str(self.xfer_db),
                    }
                },
                base=self.root,
            )
        self.assertTrue(p.execute_enabled)
        self.assertEqual(p.backend, "http_put")


if __name__ == "__main__":
    unittest.main()
