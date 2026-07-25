"""Phase 2 runtime tests."""

import sys
import unittest

from runtime.service_bus import ServiceBus
from runtime.services import ServiceManager, ServiceSpec
from runtime.health import HealthMonitor
from kernel.boot import boot, shutdown


class ServiceBusTest(unittest.TestCase):
    def test_publish_subscribe(self):
        bus = ServiceBus()
        seen = []
        bus.subscribe("test", lambda p: seen.append(p))
        bus.publish("test", {"x": 1})
        self.assertEqual(seen, [{"x": 1}])


class ServiceManagerTest(unittest.TestCase):
    def test_register_and_start_ipc_worker(self):
        mgr = ServiceManager()
        mgr.register(
            ServiceSpec(
                name="code-worker",
                command=[sys.executable, "-m", "agents.code.subprocess_runner"],
                ipc=True,
            )
        )
        self.assertTrue(mgr.start("code-worker"))
        result = mgr.call("code-worker", "ping")
        self.assertTrue(result.get("pong"))
        mgr.stop("code-worker")

    def test_status_reports_state(self):
        mgr = ServiceManager()
        mgr.register(ServiceSpec("x", ["echo", "hi"]))
        status = mgr.status()
        self.assertIn("x", status["services"])


class HealthMonitorTest(unittest.TestCase):
    def setUp(self):
        shutdown()
        boot()

    def tearDown(self):
        shutdown()

    def test_collect_includes_kernel(self):
        health = HealthMonitor()
        report = health.collect()
        self.assertIn("kernel", report["components"])
        self.assertIn("healthy", report)


class KerrdTest(unittest.TestCase):
    def test_health_report(self):
        shutdown()
        boot()
        from runtime.kerrd import Kerrd

        k = Kerrd()
        report = k.health_report()
        self.assertIn("components", report)
        shutdown()


if __name__ == "__main__":
    unittest.main()
