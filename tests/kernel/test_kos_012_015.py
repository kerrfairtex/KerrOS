"""Tests for KOS-012 through KOS-015."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kernel.access import detect_tool, get_dispatch_port, memory_query, run_tool
from kernel.boot import boot, shutdown
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
