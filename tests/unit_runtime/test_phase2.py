"""Phase 2 runtime tests."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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

    def test_collect_includes_omniroute(self):
        health = HealthMonitor()
        report = health.collect()
        self.assertIn("omniroute", report["components"])
        omni = report["components"]["omniroute"]
        self.assertEqual(omni.get("provider"), "omniroute")
        self.assertIn("status", omni)
        self.assertIn("base_url", omni)
        self.assertIn("enabled", omni)


class OmniRouteProbeTest(unittest.TestCase):
    def tearDown(self):
        for key in (
            "OMNIROUTE_ENDPOINT",
            "KERROS_OMNIROUTE_URL",
            "KERROS_USE_OMNIROUTE",
            "OMNIROUTE_API_KEY",
            "KERROS_OMNIROUTE_API_KEY",
        ):
            os.environ.pop(key, None)

    def test_resolve_url_prefers_omniroute_endpoint(self):
        from adapters.llm.omniroute_adapter import resolve_omniroute_url

        os.environ["OMNIROUTE_ENDPOINT"] = "http://omni.example/v1"
        os.environ["KERROS_OMNIROUTE_URL"] = "http://legacy.example/v1"
        self.assertEqual(resolve_omniroute_url({}), "http://omni.example/v1")

    def test_resolve_url_falls_back_to_kerros_env(self):
        from adapters.llm.omniroute_adapter import resolve_omniroute_url

        os.environ["KERROS_OMNIROUTE_URL"] = "http://legacy.example/v1"
        self.assertEqual(resolve_omniroute_url({}), "http://legacy.example/v1")

    def test_resolve_url_uses_config(self):
        from adapters.llm.omniroute_adapter import resolve_omniroute_url

        self.assertEqual(
            resolve_omniroute_url({"omniroute_url": "http://cfg.example/v1"}),
            "http://cfg.example/v1",
        )

    @patch("adapters.llm.omniroute_adapter.requests.get")
    def test_probe_disabled_when_gateway_down(self, mock_get):
        from adapters.llm.omniroute_adapter import probe_omniroute

        mock_get.side_effect = ConnectionError("refused")
        os.environ.pop("KERROS_USE_OMNIROUTE", None)
        result = probe_omniroute(base_url="http://127.0.0.1:9/v1")
        self.assertFalse(result["enabled"])
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(result["available"])

    @patch("adapters.llm.omniroute_adapter.requests.get")
    def test_probe_ok_when_enabled_and_up(self, mock_get):
        from adapters.llm.omniroute_adapter import probe_omniroute

        mock_get.return_value = MagicMock(status_code=200)
        os.environ["KERROS_USE_OMNIROUTE"] = "1"
        os.environ["OMNIROUTE_ENDPOINT"] = "http://127.0.0.1:20128/v1"
        result = probe_omniroute()
        self.assertTrue(result["enabled"])
        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "ok")
        mock_get.assert_called()
        self.assertIn("/models", mock_get.call_args[0][0])

    @patch("adapters.llm.omniroute_adapter.requests.get")
    def test_probe_unavailable_marks_enabled_down(self, mock_get):
        from adapters.llm.omniroute_adapter import probe_omniroute

        mock_get.side_effect = ConnectionError("refused")
        os.environ["KERROS_USE_OMNIROUTE"] = "1"
        result = probe_omniroute(base_url="http://127.0.0.1:9/v1")
        self.assertTrue(result["enabled"])
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["available"])

    @patch("adapters.llm.omniroute_adapter.probe_omniroute")
    def test_health_unhealthy_when_omniroute_enabled_down(self, mock_probe):
        shutdown()
        boot()
        mock_probe.return_value = {
            "provider": "omniroute",
            "enabled": True,
            "base_url": "http://127.0.0.1:9/v1",
            "available": False,
            "status": "unavailable",
            "error": "refused",
        }
        try:
            report = HealthMonitor().collect()
            self.assertFalse(report["healthy"])
            self.assertEqual(report["components"]["omniroute"]["status"], "unavailable")
        finally:
            shutdown()

    @patch("adapters.llm.omniroute_adapter.probe_omniroute")
    def test_health_ok_when_omniroute_disabled(self, mock_probe):
        shutdown()
        boot()
        mock_probe.return_value = {
            "provider": "omniroute",
            "enabled": False,
            "base_url": "http://127.0.0.1:20128/v1",
            "available": False,
            "status": "disabled",
        }
        try:
            report = HealthMonitor().collect()
            self.assertTrue(report["healthy"])
            self.assertEqual(report["components"]["omniroute"]["status"], "disabled")
        finally:
            shutdown()


class KerrdTest(unittest.TestCase):
    def test_health_report(self):
        shutdown()
        boot()
        from runtime.kerrd import Kerrd

        k = Kerrd()
        report = k.health_report()
        self.assertIn("components", report)
        self.assertIn("omniroute", report["components"])
        shutdown()


if __name__ == "__main__":
    unittest.main()
