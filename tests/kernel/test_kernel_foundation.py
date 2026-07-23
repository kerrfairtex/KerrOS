"""P0 kernel foundation tests."""

import os
import tempfile
import unittest
from pathlib import Path

from kernel import boot, get_kernel, resolve, shutdown
from kernel.config import load_config
from kernel.container import Container
from kernel.contract import (
    BootPhase,
    KernelNotReadyError,
    ServiceAlreadyRegisteredError,
    ServiceNotFoundError,
)
from kernel.boot import Kernel


class ContainerTest(unittest.TestCase):
    def test_register_and_resolve_singleton(self):
        c = Container()
        c.register("x", lambda: {"n": 1})
        self.assertEqual(c.resolve("x")["n"], 1)
        self.assertIs(c.resolve("x"), c.resolve("x"))

    def test_transient_factory(self):
        c = Container()
        c.register("n", lambda: object(), singleton=False)
        self.assertIsNot(c.resolve("n"), c.resolve("n"))

    def test_duplicate_registration_raises(self):
        c = Container()
        c.register("a", lambda: 1)
        with self.assertRaises(ServiceAlreadyRegisteredError):
            c.register("a", lambda: 2)

    def test_missing_service_raises(self):
        c = Container()
        with self.assertRaises(ServiceNotFoundError):
            c.resolve("missing")


class KernelConfigTest(unittest.TestCase):
    def test_load_config_from_workspace(self):
        cfg = load_config(base=Path(__file__).resolve().parent.parent)
        self.assertTrue(cfg.base.exists() or (cfg.base / "config.json").exists() or cfg.values)
        self.assertIsNotNone(cfg.workspace)


class KernelBootTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        os.environ["KERROS_WORKSPACE"] = tempfile.mkdtemp()

    def tearDown(self):
        shutdown()

    def test_boot_reaches_ready(self):
        k = boot()
        self.assertEqual(k.phase, BootPhase.READY)
        self.assertIsNotNone(k.booted_at)

    def test_boot_registers_services(self):
        boot()
        names = get_kernel().container.names()
        for svc in (
            "config", "router", "tool_port", "llm_port", "memory_port",
            "dispatch_port", "decision_log", "service_manager", "health_monitor",
        ):
            self.assertIn(svc, names)

    def test_resolve_before_boot_raises(self):
        k = Kernel()
        with self.assertRaises(KernelNotReadyError):
            k.resolve("config")

    def test_resolve_config_after_boot(self):
        boot()
        cfg = resolve("config")
        self.assertIsNotNone(cfg.workspace)

    def test_shutdown_resets_phase(self):
        k = boot()
        k.shutdown()
        self.assertEqual(k.phase, BootPhase.INIT)

    def test_double_boot_is_idempotent(self):
        k1 = boot()
        k2 = boot()
        self.assertIs(k1, k2)
        self.assertEqual(k1.phase, BootPhase.READY)

    def test_status_includes_boot_log(self):
        k = boot()
        status = k.status()
        self.assertEqual(status["phase"], "ready")
        self.assertIn("config", status["boot_log"])
        self.assertIn("ready", status["boot_log"])


if __name__ == "__main__":
    unittest.main()
