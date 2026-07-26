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
                self.assertEqual(
                    memory_query("logging audit trails", top_k=2),
                    rag_store.search("logging audit trails", top_k=2),
                )
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


if __name__ == "__main__":
    unittest.main()
