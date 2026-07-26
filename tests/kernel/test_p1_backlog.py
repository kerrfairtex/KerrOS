"""P1 backlog tests: decision log, adapters, watchdog."""

import copy
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
    def test_query_returns_tuples(self):
        adapter = RagStoreAdapter()
        result = adapter.query("security", top_k=2)
        self.assertIsInstance(result, list)
        if result:
            self.assertEqual(len(result[0]), 3)


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
