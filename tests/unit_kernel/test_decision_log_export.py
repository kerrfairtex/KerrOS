"""ADR-017: hash chain + JSONL export for decision_log."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from adapters.audit.decision_log_export import export_decision_log_jsonl, line_hmac
from kernel.decision_log import DecisionLog, GENESIS_HASH
from scripts.export_decision_log import main as export_main


class DecisionLogChainTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Path(self._tmpdir.name) / "decisions.db"
        self.log = DecisionLog(self.db)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_empty_chain_ok(self):
        result = self.log.verify_chain()
        self.assertTrue(result["ok"])
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["tip"], GENESIS_HASH)

    def test_chain_links_records(self):
        self.log.record("a", "t", "one", "ok", "", timestamp=1.0)
        self.log.record("a", "t", "two", "ok", "", timestamp=2.0)
        result = self.log.verify_chain()
        self.assertTrue(result["ok"])
        self.assertEqual(result["checked"], 2)
        rows = list(self.log.iter_from(0))
        self.assertEqual(rows[0].prev_hash, GENESIS_HASH)
        self.assertEqual(rows[1].prev_hash, rows[0].entry_hash)
        self.assertTrue(rows[0].entry_hash)
        self.assertTrue(rows[1].entry_hash)

    def test_tamper_detected(self):
        self.log.record("a", "t", "one", "ok", "", timestamp=1.0)
        self.log.record("a", "t", "two", "ok", "", timestamp=2.0)
        with sqlite3.connect(str(self.db)) as conn:
            conn.execute(
                "UPDATE decisions SET outcome = ? WHERE id = 1",
                ("tampered",),
            )
            conn.commit()
        result = self.log.verify_chain()
        self.assertFalse(result["ok"])
        self.assertEqual(result["broken_at"], 1)
        self.assertEqual(result["error"], "entry_hash mismatch")

    def test_legacy_migration_backfill(self):
        legacy = Path(self._tmpdir.name) / "legacy.db"
        with sqlite3.connect(str(legacy)) as conn:
            conn.execute(
                """
                CREATE TABLE decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    actor TEXT NOT NULL,
                    decision_type TEXT NOT NULL,
                    input_summary TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                INSERT INTO decisions
                    (timestamp, actor, decision_type, input_summary, outcome, reason)
                VALUES (1.0, 'old', 'scope_check', 'x', 'denied', '')
                """
            )
            conn.commit()
        log = DecisionLog(legacy)
        result = log.verify_chain()
        self.assertTrue(result["ok"])
        self.assertEqual(result["checked"], 1)
        row = next(log.iter_from(0))
        self.assertEqual(row.prev_hash, GENESIS_HASH)
        self.assertTrue(row.entry_hash)


class DecisionLogExportTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Path(self._tmpdir.name) / "decisions.db"
        self.log = DecisionLog(self.db)
        self.log.record("a", "t", "one", "ok", "", timestamp=1.0)
        self.log.record("a", "t", "two", "ok", "", timestamp=2.0)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_export_jsonl_roundtrip(self):
        out = Path(self._tmpdir.name) / "audit.jsonl"
        result = export_decision_log_jsonl(out, log=self.log)
        self.assertTrue(result["ok"])
        self.assertEqual(result["exported"], 2)
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["input_summary"], "one")
        self.assertIn("entry_hash", first)

    def test_export_refuses_broken_chain(self):
        with sqlite3.connect(str(self.db)) as conn:
            conn.execute(
                "UPDATE decisions SET outcome = ? WHERE id = 2",
                ("nope",),
            )
            conn.commit()
        out = Path(self._tmpdir.name) / "broken.jsonl"
        result = export_decision_log_jsonl(out, log=self.log)
        self.assertFalse(result["ok"])
        self.assertEqual(result["exported"], 0)
        self.assertFalse(out.exists())

    def test_export_with_hmac(self):
        out = Path(self._tmpdir.name) / "signed.jsonl"
        result = export_decision_log_jsonl(
            out, log=self.log, hmac_secret="test-secret"
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["hmac"])
        line = out.read_text(encoding="utf-8").strip().splitlines()[0]
        obj = json.loads(line)
        mac = obj.pop("line_hmac")
        body = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        self.assertEqual(mac, line_hmac(body, "test-secret"))

    def test_cli_verify_only(self):
        rc = export_main(["--db", str(self.db), "--verify-only"])
        self.assertEqual(rc, 0)

    def test_cli_export(self):
        dest = Path(self._tmpdir.name) / "cli.jsonl"
        rc = export_main(["--db", str(self.db), "-o", str(dest)])
        self.assertEqual(rc, 0)
        self.assertTrue(dest.is_file())


class PortAuditHookTest(unittest.TestCase):
    def test_router_adapter_logs_run_tool(self):
        from unittest.mock import patch

        from adapters.tools.router_adapter import RouterAdapter

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.db"
            log = DecisionLog(db)
            with patch("kernel.decision_log.get_decision_log", return_value=log):
                with patch("kernel.router.run_tool", return_value="ok"):
                    RouterAdapter().run_tool("calc", "1+1")
            rows = list(log.iter_from(0))
            self.assertTrue(any(r.decision_type == "run_tool" for r in rows))
            self.assertTrue(any(r.actor == "tool_port" for r in rows))

    def test_rag_adapter_logs_upsert(self):
        from unittest.mock import patch

        from adapters.memory.rag_store_adapter import RagStoreAdapter

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "d.db"
            log = DecisionLog(db)
            with patch("kernel.decision_log.get_decision_log", return_value=log):
                with patch("rag.store.ingest_text"):
                    RagStoreAdapter().upsert("hello world", "unit-src")
            rows = list(log.iter_from(0))
            self.assertTrue(any(r.decision_type == "upsert" for r in rows))
            self.assertIn("source:unit-src", rows[0].input_summary)


if __name__ == "__main__":
    unittest.main()
