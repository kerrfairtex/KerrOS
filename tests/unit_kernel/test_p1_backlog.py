"""P1 backlog tests: decision log, adapters, watchdog."""

import copy
import os
import subprocess
import sys
import tempfile
import unittest
from multiprocessing import Queue, get_context
from pathlib import Path

from kernel.boot import boot, shutdown
from kernel import router as kernel_router
from kernel.decision_log import DecisionLog
from adapters.memory.rag_store_adapter import RagStoreAdapter
from adapters.memory.hybrid_memory_adapter import HybridMemoryAdapter
from adapters.tools.router_adapter import RouterAdapter
from rag import store as rag_store
from tools.scope_gate import check, arm_deploy, disarm_deploy


def _decision_log_process_writer(
    db_path: str,
    start: int,
    count: int,
    error_queue: Queue,
) -> None:
    """Write a range of records from a child process and report failures to parent."""
    try:
        log = DecisionLog(Path(db_path))
        for i in range(start, start + count):
            log.record("proc", "concurrent", f"item-{i}", "ok", "")
    except Exception as exc:  # pragma: no cover - unexpected failure condition
        error_queue.put(str(exc))


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
        ctx = get_context("spawn")
        error_queue = ctx.Queue()
        writes_per_process = 25
        p1 = ctx.Process(
            target=_decision_log_process_writer,
            args=(str(self.db), 0, writes_per_process, error_queue),
        )
        p2 = ctx.Process(
            target=_decision_log_process_writer,
            args=(str(self.db), writes_per_process, writes_per_process, error_queue),
        )
        p1.start()
        p2.start()
        p1.join()
        p2.join()
        self.assertEqual(p1.exitcode, 0)
        self.assertEqual(p2.exitcode, 0)
        proc_errors = []
        while not error_queue.empty():
            proc_errors.append(error_queue.get())
        self.assertEqual(proc_errors, [])
        self.assertEqual(self.log.count(), writes_per_process * 2)


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

    def test_fts_search_returns_matches(self):
        rag_store.ingest_text(
            "Kernel routing policy enforces unified endpoint fallbacks with deterministic memory recall.",
            source="kernel_design",
        )
        results = rag_store.search_fts("unified endpoint deterministic memory", top_k=2)
        self.assertTrue(results)
        self.assertIn("unified endpoint", results[0][1].lower())


class HybridMemoryAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_db_path = rag_store.DB_PATH
        rag_store.DB_PATH = str(Path(self._tmpdir.name) / "rag_store.db")
        rag_store._ensure_schema()

    def tearDown(self):
        rag_store.DB_PATH = self._old_db_path
        self._tmpdir.cleanup()

    def test_query_hybrid_returns_keyword_hits_without_qdrant(self):
        adapter = HybridMemoryAdapter()
        adapter.upsert(
            "Qdrant vector recall is optional while SQLite FTS keyword recall remains deterministic.",
            "memory_design",
        )
        hits = adapter.query("sqlite deterministic recall", top_k=2)
        self.assertTrue(hits)
        self.assertTrue(any("deterministic" in row[1].lower() for row in hits))


class RouterAdapterTest(unittest.TestCase):
    def test_detect_tool_dispatch(self):
        adapter = RouterAdapter()
        tool, args = adapter.dispatch("detect_tool", "run ls")
        self.assertEqual(tool, "bash")

    def test_detect_tool_parity_with_kernel_router(self):
        adapter = RouterAdapter()
        cases = [
            {"text": "run ls", "bypass_gate": False, "expected_tool": "bash"},
            {"text": "nmap 8.8.8.8", "bypass_gate": True, "expected_tool": "nmap"},
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                actual = adapter.dispatch("detect_tool", payload)
                expected = kernel_router.detect_tool(payload["text"], bypass_gate=payload["bypass_gate"])
                self.assertEqual(actual, expected)
                self.assertEqual(actual[0], payload["expected_tool"])

    def test_run_tool_dispatch(self):
        adapter = RouterAdapter()
        out = adapter.dispatch("run_tool", {"tool": "calc", "args": "2+2"})
        self.assertIn("4", out)

    def test_detect_domain_parity_with_kernel_router(self):
        adapter = RouterAdapter()
        cases = [
            ("run nmap 8.8.8.8", "network"),
            ("check owasp xss", "web_security"),
        ]
        for payload, expected_domain in cases:
            with self.subTest(payload=payload):
                actual = adapter.dispatch("detect_domain", payload)
                expected = kernel_router.detect_domain(payload)
                self.assertEqual(actual, expected)
                self.assertEqual(actual, expected_domain)


class ScopeGateAuditTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        os.environ["KERROS_WORKSPACE"] = tempfile.mkdtemp()
        boot()
        # Snapshot scope state so tests that add/arm targets can restore it,
        # since scope_gate persists to the repository base's
        # config/scope.json (resolved via kernel.config.load_config().scope_path),
        # and KERROS_WORKSPACE only isolates the workspace, not scope storage.
        from tools.scope_gate import _load_scope

        self._scope_snapshot = copy.deepcopy(_load_scope())

    def tearDown(self):
        from tools.scope_gate import _save_scope

        _save_scope(self._scope_snapshot)
        shutdown()

    def test_denied_scope_creates_log_entry(self):
        allowed, _ = check("nmap", "203.0.113.1")
        self.assertFalse(allowed)
        log = boot().container.resolve("decision_log")
        rows = log.read_recent(5)
        types = [r.decision_type for r in rows]
        self.assertIn("scope_check", types)
        row = next(r for r in rows if r.decision_type == "scope_check")
        self.assertEqual(row.outcome, "denied")

    def test_allowed_scope_check_is_also_logged(self):
        from tools.scope_gate import add_target

        add_target("203.0.113.1")
        allowed, _ = check("nmap", "203.0.113.1")
        self.assertTrue(allowed)
        log = boot().container.resolve("decision_log")
        rows = log.read_recent(10)
        scope_checks = [r for r in rows if r.decision_type == "scope_check"]
        self.assertTrue(any(r.outcome == "allowed" for r in scope_checks))

    def test_scope_add_and_remove_logged(self):
        from tools.scope_gate import add_target, remove_target

        add_target("example.test")
        remove_target("example.test")
        log = boot().container.resolve("decision_log")
        types = [r.decision_type for r in log.read_recent(10)]
        self.assertIn("scope_add", types)
        self.assertIn("scope_remove", types)

    def test_arm_disarm_logged(self):
        arm_deploy(1)
        disarm_deploy()
        log = boot().container.resolve("decision_log")
        rows = log.read_recent(10)
        types = [r.decision_type for r in rows]
        self.assertIn("deploy_arm", types)
        outcomes = [r.outcome for r in rows if r.decision_type == "deploy_arm"]
        self.assertIn("armed", outcomes)
        self.assertIn("disarmed", outcomes)

    def test_deploy_check_allowed_and_denied_logged(self):
        allowed, _ = check("github_push", ())
        self.assertFalse(allowed)
        arm_deploy(1)
        allowed, _ = check("github_push", ())
        self.assertTrue(allowed)
        log = boot().container.resolve("decision_log")
        deploy_checks = [r for r in log.read_recent(10) if r.decision_type == "deploy_check"]
        outcomes = {r.outcome for r in deploy_checks}
        self.assertIn("denied", outcomes)
        self.assertIn("allowed", outcomes)


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
