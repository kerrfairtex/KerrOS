"""Phase 3 runtime and LLM adapter tests."""

import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from runtime.event_bus import EventBus
from runtime.scheduler import Scheduler
from runtime.workflows import WorkflowDefinition, WorkflowStep, WorkflowEngine, WorkflowState
from kernel.boot import boot, shutdown


class EventBusTest(unittest.TestCase):
    def test_publish_subscribe_and_wildcard(self):
        bus = EventBus()
        seen = []
        bus.subscribe("test.topic", lambda e: seen.append(e.topic))
        bus.subscribe("*", lambda e: seen.append("wildcard"))
        bus.publish("test.topic", {"x": 1})
        self.assertIn("test.topic", seen)
        self.assertIn("wildcard", seen)

    def test_recent_and_stats(self):
        bus = EventBus()
        bus.publish("a", {"n": 1})
        bus.publish("b", {"n": 2})
        self.assertEqual(len(bus.recent(1)), 1)
        self.assertEqual(bus.stats()["events"], 2)


class SchedulerTest(unittest.TestCase):
    def test_schedule_once_fires(self):
        bus = EventBus()
        fired = []
        bus.subscribe("scheduler.job.fired", lambda e: fired.append(e.payload))
        sched = Scheduler(bus=bus)
        sched.start(tick_s=0.1)
        sched.schedule_once("test", 0.2, callback=lambda: "ok")
        time.sleep(0.6)
        sched.stop()
        self.assertTrue(fired)

    def test_schedule_interval(self):
        bus = EventBus()
        sched = Scheduler(bus=bus)
        job_id = sched.schedule_interval("tick", 0.3)
        jobs = sched.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertTrue(sched.cancel(job_id))


class WorkflowEngineTest(unittest.TestCase):
    def test_dag_execution(self):
        bus = EventBus()
        engine = WorkflowEngine(bus=bus)
        engine.register(
            WorkflowDefinition(
                name="sum",
                steps=[
                    WorkflowStep("a", action=lambda ctx: 1),
                    WorkflowStep("b", action=lambda ctx: ctx["a"] + 2, depends_on=["a"]),
                ],
            )
        )
        run = engine.run("sum")
        self.assertEqual(run.state, WorkflowState.COMPLETED)
        self.assertEqual(run.results["b"], 3)

    def test_deadlock_raises(self):
        engine = WorkflowEngine()
        with self.assertRaises(ValueError):
            engine.register(
                WorkflowDefinition(
                    name="bad",
                    steps=[
                        WorkflowStep("a", action=lambda ctx: 1, depends_on=["b"]),
                        WorkflowStep("b", action=lambda ctx: 2, depends_on=["a"]),
                    ],
                )
            )

    def test_register_persists_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "catalog.json"
            engine = WorkflowEngine(catalog_path=catalog)
            engine.register(
                WorkflowDefinition(
                    name="build.docs",
                    steps=[WorkflowStep("draft", action=lambda ctx: "ok")],
                    description="Generate docs workflow",
                )
            )
            self.assertTrue(catalog.exists())
            entries = engine.list_catalog()
            self.assertTrue(any(e["name"] == "build.docs" for e in entries))


class KernelPhase3Test(unittest.TestCase):
    def setUp(self):
        shutdown()
        boot()

    def tearDown(self):
        shutdown()

    def test_kernel_registers_phase3_services(self):
        from kernel import resolve, get_kernel

        names = get_kernel().status()["services"]
        self.assertIn("event_bus", names)
        self.assertIn("scheduler", names)
        self.assertIn("workflow_engine", names)
        bus = resolve("event_bus")
        sched = resolve("scheduler")
        wf = resolve("workflow_engine")
        port = resolve("llm_port")
        self.assertIsNotNone(bus)
        self.assertIsNotNone(sched)
        self.assertIsNotNone(wf)
        self.assertTrue(hasattr(port, "complete"))
        status = port.status()
        self.assertIn("default_provider", status)


class OpenAICompatTest(unittest.TestCase):
    @patch("adapters.llm.openai_compat.requests.post")
    @patch("adapters.llm.openai_compat.requests.get")
    def test_complete_parses_response(self, mock_get, mock_post):
        from adapters.llm.openai_compat import OpenAICompatClient

        mock_get.return_value = MagicMock(status_code=200)
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "hello"}}]},
        )
        client = OpenAICompatClient(
            base_url="http://localhost:11434/v1",
            model="test",
            provider_name="test",
        )
        result = client.complete("hi")
        self.assertEqual(result, "hello")


class CompositeLLMTest(unittest.TestCase):
    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_cloud")
    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_ollama")
    def test_provider_hint_ollama(self, mock_get_ollama, mock_get_cloud):
        from adapters.llm.composite_adapter import CompositeLLMAdapter

        ollama = MagicMock()
        ollama.status.return_value = {"available": True}
        ollama.complete.return_value = "local response"
        mock_get_ollama.return_value = ollama
        mock_get_cloud.return_value = MagicMock()

        adapter = CompositeLLMAdapter()
        result = adapter.complete("test", provider_hint="ollama")
        self.assertEqual(result, "local response")
        self.assertEqual(adapter.last_api_used(), "ollama")

    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_cloud")
    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_omniroute")
    def test_provider_hint_omniroute_falls_back_to_cloud(self, mock_get_omniroute, mock_get_cloud):
        from adapters.llm.composite_adapter import CompositeLLMAdapter

        omniroute = MagicMock()
        omniroute.complete.side_effect = RuntimeError("omniroute down")
        omniroute.status.return_value = {"enabled": True}
        cloud = MagicMock()
        cloud.complete.return_value = "cloud fallback"
        mock_get_omniroute.return_value = omniroute
        mock_get_cloud.return_value = cloud

        adapter = CompositeLLMAdapter()
        result = adapter.complete("test", provider_hint="omniroute")
        self.assertEqual(result, "cloud fallback")
        self.assertEqual(adapter.last_api_used(), "cloud")


class AdaptiveEngineLLMPortTest(unittest.TestCase):
    @patch("kernel.access.get_llm_port")
    def test_init_online_uses_llm_port_complete(self, mock_get_llm_port):
        from core.adaptive_engine import AdaptiveEngine

        port = MagicMock()
        port.complete.return_value = "hello"
        mock_get_llm_port.return_value = port

        engine = AdaptiveEngine()
        ok, mode = engine.init_online()

        self.assertTrue(ok)
        self.assertEqual(mode, "online")
        port.complete.assert_called_once_with("hi", max_tokens=5)

    @patch("builtins.print")
    def test_online_generate_filters_history(self, mock_print):
        from core.adaptive_engine import AdaptiveEngine

        port = MagicMock()
        port.complete.return_value = "done"
        port.last_api_used.return_value = "cloud"

        engine = AdaptiveEngine()
        engine.mode = "online"
        engine._llm_port = port

        history = [
            {"role": "user", "content": "keep this"},
            {"role": "assistant", "content": "[Tool output] drop this"},
            {"role": "system", "content": "drop role"},
            {"role": "assistant", "content": "ok reply"},
        ]

        result = engine._online_generate("solve this", "sys", history, stream=False)

        self.assertEqual(result, "done")
        port.complete.assert_called_once_with(
            "solve this",
            system="sys",
            history=[
                {"role": "user", "content": "keep this"},
                {"role": "assistant", "content": "ok reply"},
            ],
            max_tokens=4096,
        )
        port.last_api_used.assert_called_once_with()
        mock_print.assert_called_once()


if __name__ == "__main__":
    unittest.main()
