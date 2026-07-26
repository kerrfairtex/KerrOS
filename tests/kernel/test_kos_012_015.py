"""Tests for KOS-012 through KOS-015."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kernel.access import detect_tool, get_dispatch_port, memory_query, memory_upsert, run_tool
from kernel.boot import boot, shutdown
from rag import store as rag_store
from runtime.ipc import JsonLineClient, spawn_worker


class IpcTest(unittest.TestCase):
    def test_worker_ping(self):
        proc = spawn_worker([sys.executable, "-m", "agents.code.subprocess_runner"])
        client = JsonLineClient(proc)
        result = client.call("ping")
        self.assertTrue(result.get("pong"))
        client.close()


class IsolatedExecutorTest(unittest.TestCase):
    def test_parent_survives_worker_crash(self):
        proc = spawn_worker([sys.executable, "-m", "agents.code.subprocess_runner"])
        client = JsonLineClient(proc)
        with self.assertRaises(Exception):
            client.call("crash")
        self.assertIsNotNone(proc.poll())
        client.close()

        proc2 = spawn_worker([sys.executable, "-m", "agents.code.subprocess_runner"])
        client2 = JsonLineClient(proc2)
        self.assertTrue(client2.call("ping").get("pong"))
        client2.close()


class IsolatedCodeExecutorRestartTest(unittest.TestCase):
    """End-to-end: IsolatedCodeExecutor recovers from a worker crash and
    the crash+restart is recorded in decision_log (KOS-012 DoD)."""

    def setUp(self):
        import kernel.decision_log as decision_log_module

        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_log = decision_log_module._log
        decision_log_module._log = decision_log_module.DecisionLog(
            Path(self._tmpdir.name) / "decisions.db"
        )

    def tearDown(self):
        import kernel.decision_log as decision_log_module

        decision_log_module._log = self._orig_log
        self._tmpdir.cleanup()

    def test_executor_restarts_after_crash_and_logs_decision(self):
        from agents.code.isolated_executor import IsolatedCodeExecutor
        from kernel.decision_log import get_decision_log
        from runtime.ipc import IpcError

        executor = IsolatedCodeExecutor()
        try:
            with tempfile.TemporaryDirectory() as workdir:
                script = Path(workdir) / "ok.py"
                script.write_text("print('hi')\n")

                result = executor.run_and_verify(str(script))
                self.assertTrue(result.get("ran"))
                self.assertTrue(result.get("ok"))

                pre_restart_ids = {
                    r.id
                    for r in get_decision_log().read_recent(limit=100)
                }

                # Simulate a crash inside the worker subprocess. IsolatedCodeExecutor
                # has no public "send arbitrary method" API (by design — only
                # run_and_verify is exposed), so this reaches into the internal
                # client to trigger the same worker-death path run_and_verify hits.
                with self.assertRaises(IpcError):
                    executor._client.call("crash")

                # The parent process must survive and transparently recover.
                result2 = executor.run_and_verify(str(script))
                self.assertTrue(result2.get("ran"))
                self.assertTrue(result2.get("ok"))

            records = get_decision_log().read_recent(limit=100)
            new_records = [r for r in records if r.id not in pre_restart_ids]
            restart_records = [
                r for r in new_records
                if r.actor == "code_executor" and r.decision_type == "worker_restart"
            ]
            self.assertEqual(
                len(restart_records), 1,
                "expected exactly one worker_restart decision to be logged",
            )
            self.assertEqual(restart_records[0].outcome, "restarted")
            self.assertIn(
                "agents.code.subprocess_runner", restart_records[0].input_summary
            )
        finally:
            executor.close()


class PortAccessTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        boot()

    def tearDown(self):
        shutdown()

    def test_dispatch_port_detect_tool(self):
        tool, args = detect_tool("run ls")
        self.assertEqual(tool, "bash")

    def test_dispatch_port_run_calc(self):
        out = run_tool("calc", "2+2")
        self.assertIn("4", out)

    def test_memory_query_returns_list(self):
        hits = memory_query("security", top_k=2)
        self.assertIsInstance(hits, list)

    def test_memory_access_facade_matches_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_db_path = rag_store.DB_PATH
            rag_store.DB_PATH = str(Path(tmp) / "rag_store.db")
            try:
                rag_store._ensure_schema()
                memory_upsert(
                    "Python logging hardening guidance for secure audit trails and incident response.",
                    "NIST_logging",
                )
                hits = memory_query("logging audit trails", top_k=2)
                self.assertIsInstance(hits, list)
                self.assertTrue(hits)
                self.assertTrue(any("logging" in h[1].lower() for h in hits))
            finally:
                rag_store.DB_PATH = old_db_path


class CompletionCoordinatorTest(unittest.TestCase):
    def test_coordinator_import(self):
        from core.completion_runtime_coordinator import CompletionRuntimeCoordinator, coordinator

        self.assertIsInstance(coordinator, CompletionRuntimeCoordinator)

    def test_kernel_shim_aliases_coordinator(self):
        import warnings
        from core.completion_runtime_coordinator import CompletionRuntimeCoordinator

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from core.completion_runtime_kernel import kernel, CompletionRuntimeKernel

        self.assertTrue(len(w) >= 1)
        self.assertTrue(hasattr(kernel, "execute"))
        self.assertIs(CompletionRuntimeKernel, CompletionRuntimeCoordinator)


class OrphanedCoreClusterTest(unittest.TestCase):
    """KOS-015: Verify the orphaned core/ orchestration cluster has been removed."""

    REMOVED_MODULES = [
        "core.agent_gateway",
        "core.agent_router",
        "core.unified_agent_gateway",
        "core.completion_activation",
        "core.completion_orchestrator",
        "core.completion_stack",
    ]

    def test_orphaned_modules_are_not_importable(self):
        for module in self.REMOVED_MODULES:
            with self.subTest(module=module):
                with self.assertRaises(ImportError, msg=f"{module} should not exist"):
                    __import__(module)

    def test_orphaned_files_do_not_exist(self):
        repo_root = Path(__file__).resolve().parents[2]
        for module in self.REMOVED_MODULES:
            rel_path = module.replace(".", "/") + ".py"
            full_path = repo_root / rel_path
            self.assertFalse(
                full_path.exists(),
                msg=f"{rel_path} still present on disk",
            )

    def test_control_plane_loads_without_stack(self):
        from core.completion_control_plane import CompletionControlPlane

        cp = CompletionControlPlane()
        status = cp.status()
        self.assertIn("uptime", status)
        self.assertNotIn("stack", status)

    def test_agent_registry_sync_loads_without_gateway(self):
        from core.agent_registry_sync import AgentRegistrySync

        sync = AgentRegistrySync()
        self.assertFalse(hasattr(sync, "gateway"))

    def test_completion_runtime_loads_without_orchestrator(self):
        from core.completion_runtime import CompletionRuntime

        rt = CompletionRuntime()
        self.assertFalse(hasattr(rt, "orchestrator"))
        health = rt.health()
        self.assertEqual(health["status"], "online")
        self.assertNotIn("orchestrator", health)


if __name__ == "__main__":
    unittest.main()
