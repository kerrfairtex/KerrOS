"""P1 backlog tests: decision log, adapters, watchdog."""

import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from kernel.boot import boot, shutdown
from kernel.decision_log import DecisionLog
from adapters.memory.rag_store_adapter import RagStoreAdapter
from adapters.tools.router_adapter import RouterAdapter
from rag import store as rag_store
from tools.scope_gate import check, arm_deploy, disarm_deploy


class DecisionLogTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Path(self._tmpdir.name) / "decisions.db"
        self.log = DecisionLog(self.db)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_append_only_record_and_read(self):
        rid = self.log.record("test", "scope_check", "nmap:1.2.3.4", "denied", "not in scope")
        self.assertGreater(rid, 0)
        rows = self.log.read_recent(10)
        self.assertEqual(rows[0].outcome, "denied")
        self.assertEqual(self.log.count(), 1)

    def test_concurrent_writes(self):
        errors = []

        def writer(i):
            try:
                self.log.record("t", "concurrent", f"item-{i}", "ok", "")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.log.count(), 20)


class RagStoreAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_db_path = rag_store.DB_PATH
        rag_store.DB_PATH = str(Path(self._tmpdir.name) / "rag_store.db")
        rag_store._ensure_schema()

    def tearDown(self):
        rag_store.DB_PATH = self._old_db_path
        self._tmpdir.cleanup()

    def test_query_matches_store_search(self):
        rag_store.ingest_text(
            "Security hardening guidance for SQL injection prevention and safe query handling.",
            source="OWASP_Cheat_Sheet",
        )
        adapter = RagStoreAdapter()
        self.assertEqual(
            adapter.query("security query handling", top_k=2),
            rag_store.search("security query handling", top_k=2),
        )

    def test_category_and_exact_id_queries_match_store(self):
        rag_store.ingest_text(
            "CVE-2026-9999 remote code execution vulnerability with kernel memory corruption details.",
            source="CVE_feed",
        )
        adapter = RagStoreAdapter()
        self.assertEqual(
            adapter.search_by_category("remote code execution", "cve", top_k=2),
            rag_store.search_by_category("remote code execution", "cve", top_k=2),
        )
        self.assertEqual(
            adapter.search_exact_id("Tell me about CVE-2026-9999"),
            rag_store.search_exact_id("Tell me about CVE-2026-9999"),
        )


class RouterAdapterTest(unittest.TestCase):
    def test_detect_tool_dispatch(self):
        adapter = RouterAdapter()
        tool, args = adapter.dispatch("detect_tool", "run ls")
        self.assertEqual(tool, "bash")

    def test_run_tool_dispatch(self):
        adapter = RouterAdapter()
        out = adapter.dispatch("run_tool", {"tool": "calc", "args": "2+2"})
        self.assertIn("4", out)


class ScopeGateAuditTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        os.environ["KERROS_WORKSPACE"] = tempfile.mkdtemp()
        boot()

    def tearDown(self):
        shutdown()

    def test_denied_scope_creates_log_entry(self):
        allowed, _ = check("nmap", "203.0.113.1")
        self.assertFalse(allowed)
        log = boot().container.resolve("decision_log")
        types = [r.decision_type for r in log.read_recent(5)]
        self.assertIn("scope_check", types)

    def test_arm_disarm_logged(self):
        arm_deploy(1)
        disarm_deploy()
        log = boot().container.resolve("decision_log")
        types = [r.decision_type for r in log.read_recent(10)]
        self.assertIn("deploy_arm", types)


class VerifyAuditTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        os.environ["KERROS_WORKSPACE"] = tempfile.mkdtemp()
        boot()

    def tearDown(self):
        shutdown()

    def test_verify_identity_creates_log_entry_without_raw_pii(self):
        from kernel.router import _verify_identity

        _verify_identity("Jane Doe")
        log = boot().container.resolve("decision_log")
        rows = log.read_recent(10)
        verification_rows = [r for r in rows if r.decision_type == "verification"]
        self.assertTrue(verification_rows)
        self.assertTrue(verification_rows[0].input_summary.startswith("verify_identity:hash:"))
        self.assertNotIn("Jane Doe", verification_rows[0].input_summary)

    def test_verify_business_creates_log_entry_without_raw_pii(self):
        from kernel.router import _verify_business

        _verify_business("Acme Corp")
        log = boot().container.resolve("decision_log")
        rows = log.read_recent(10)
        verification_rows = [r for r in rows if r.decision_type == "verification"]
        self.assertTrue(verification_rows)
        self.assertTrue(verification_rows[0].input_summary.startswith("verify_business:hash:"))
        self.assertNotIn("Acme Corp", verification_rows[0].input_summary)


class WatchdogTest(unittest.TestCase):
    def test_watchdog_restarts_failing_command(self):
        from kernel.watchdog import Watchdog, WatchdogConfig

        script = (
            "import sys\n"
            "c = open(sys.argv[1]).read().strip()\n"
            "open(sys.argv[1], 'w').write(str(int(c or '0') + 1))\n"
            "sys.exit(1)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            counter = Path(tmp) / "count"
            counter.write_text("0")
            py = Path(tmp) / "fail.py"
            py.write_text(script)
            wd = Watchdog(
                [sys.executable, str(py), str(counter)],
                config=WatchdogConfig(max_restarts=2, backoff_base=0.01, backoff_cap=0.05),
            )
            wd.run()
            self.assertGreaterEqual(int(counter.read_text()), 2)


if __name__ == "__main__":
    unittest.main()
