"""P1 backlog tests: decision log, adapters, watchdog."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from multiprocessing import get_context
from pathlib import Path

from kernel.boot import boot, shutdown
from kernel.decision_log import DecisionLog
from adapters.memory.rag_store_adapter import RagStoreAdapter
from adapters.tools.router_adapter import RouterAdapter
from tools.scope_gate import check, arm_deploy, disarm_deploy


def _decision_log_process_writer(
    db_path: str,
    start: int,
    count: int,
    error_queue: object,
) -> None:
    try:
        log = DecisionLog(Path(db_path))
        for i in range(start, start + count):
            log.record("proc", "concurrent", f"item-{i}", "ok", "")
    except Exception as exc:  # pragma: no cover - captured for parent assertion
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
