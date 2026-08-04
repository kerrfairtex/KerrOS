"""P6 LLM provider circuit breaker / cooldown / lockout."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from adapters.llm.resilience import (
    CircuitState,
    ProviderCircuitRegistry,
    ResilienceConfig,
    looks_like_provider_failure,
)
from adapters.llm.composite_adapter import CompositeLLMAdapter


class ResilienceRegistryTest(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]

        def clock():
            return self.now[0]

        self.reg = ProviderCircuitRegistry(
            config=ResilienceConfig(
                enabled=True,
                failure_threshold=2,
                cooldown_s=10.0,
                lockout_opens=2,
                lockout_s=60.0,
            ),
            clock=clock,
        )

    def test_opens_after_threshold(self):
        self.assertTrue(self.reg.allow("ollama"))
        self.reg.record_failure("ollama", error="down")
        self.assertTrue(self.reg.allow("ollama"))
        self.reg.record_failure("ollama", error="down")
        self.assertFalse(self.reg.allow("ollama"))
        snap = self.reg.snapshot()["providers"]["ollama"]
        self.assertEqual(snap["state"], CircuitState.OPEN.value)

    def test_half_open_after_cooldown_then_close_on_success(self):
        self.reg.record_failure("vllm", error="x")
        self.reg.record_failure("vllm", error="x")
        self.assertFalse(self.reg.allow("vllm"))
        self.now[0] += 11.0
        self.assertTrue(self.reg.allow("vllm"))  # half-open probe
        self.assertFalse(self.reg.allow("vllm"))  # second concurrent probe blocked
        self.reg.record_success("vllm")
        self.assertEqual(
            self.reg.snapshot()["providers"]["vllm"]["state"],
            CircuitState.CLOSED.value,
        )
        self.assertTrue(self.reg.allow("vllm"))

    def test_half_open_fail_reopens(self):
        self.reg.record_failure("cloud", error="x")
        self.reg.record_failure("cloud", error="x")
        self.now[0] += 11.0
        self.assertTrue(self.reg.allow("cloud"))
        self.reg.record_failure("cloud", error="still down")
        self.assertEqual(
            self.reg.snapshot()["providers"]["cloud"]["state"],
            CircuitState.LOCKED.value,  # open_count reached lockout_opens=2
        )

    def test_lockout_expires(self):
        self.reg.record_failure("omniroute", permanent=True)
        self.assertEqual(
            self.reg.snapshot()["providers"]["omniroute"]["state"],
            CircuitState.OPEN.value,
        )
        self.reg.record_failure("omniroute", permanent=True)
        self.assertEqual(
            self.reg.snapshot()["providers"]["omniroute"]["state"],
            CircuitState.LOCKED.value,
        )
        self.assertFalse(self.reg.allow("omniroute"))
        self.now[0] += 61.0
        self.assertTrue(self.reg.allow("omniroute"))
        self.assertEqual(
            self.reg.snapshot()["providers"]["omniroute"]["state"],
            CircuitState.CLOSED.value,
        )

    def test_reset(self):
        self.reg.record_failure("ollama", permanent=True)
        self.assertFalse(self.reg.allow("ollama"))
        self.reg.reset("ollama")
        self.assertTrue(self.reg.allow("ollama"))

    def test_disabled_always_allows(self):
        reg = ProviderCircuitRegistry(
            config=ResilienceConfig(enabled=False, failure_threshold=1)
        )
        reg.record_failure("cloud", permanent=True)
        self.assertTrue(reg.allow("cloud"))

    def test_soft_fail_detection(self):
        self.assertTrue(looks_like_provider_failure("[All APIs failed. Use /offline mode.]"))
        self.assertFalse(looks_like_provider_failure("hello world"))


class CompositeResilienceTest(unittest.TestCase):
    def test_skips_open_provider_and_uses_next(self):
        now = [0.0]
        reg = ProviderCircuitRegistry(
            config=ResilienceConfig(
                failure_threshold=1,
                cooldown_s=30,
                lockout_opens=5,
                lockout_s=300,
            ),
            clock=lambda: now[0],
        )
        adapter = CompositeLLMAdapter(resilience=reg)
        ollama = MagicMock()
        ollama.status.return_value = {"available": True}
        ollama.complete.side_effect = RuntimeError("ollama down")
        cloud = MagicMock()
        cloud.complete.return_value = "ok from cloud"
        adapter._get_ollama = MagicMock(return_value=ollama)
        adapter._get_cloud = MagicMock(return_value=cloud)
        adapter._get_openrouter = MagicMock(
            return_value=MagicMock(status=lambda: {"available": False})
        )
        adapter._get_litellm = MagicMock(return_value=MagicMock(status=lambda: {"available": False}))
        adapter._get_vllm = MagicMock(return_value=MagicMock(status=lambda: {"available": False}))
        adapter._local_first = True
        adapter._default_provider = "ollama"

        # First call: ollama fails → open; cloud succeeds
        text = adapter.complete("hi", provider_hint="ollama")
        self.assertEqual(text, "ok from cloud")
        self.assertEqual(adapter.last_api_used(), "cloud")

        # Second call: ollama skipped by circuit; cloud used
        cloud.complete.reset_mock()
        cloud.complete.return_value = "again"
        text2 = adapter.complete("hi", provider_hint="ollama")
        self.assertEqual(text2, "again")
        ollama.complete.assert_called_once()  # only first attempt
        self.assertEqual(
            reg.snapshot()["providers"]["ollama"]["state"],
            CircuitState.OPEN.value,
        )

    def test_status_includes_resilience(self):
        adapter = CompositeLLMAdapter(
            resilience=ProviderCircuitRegistry(config=ResilienceConfig(enabled=True))
        )
        adapter._get_cloud = MagicMock(return_value=MagicMock(status=lambda: {}))
        adapter._get_openrouter = MagicMock(
            return_value=MagicMock(status=lambda: {"available": False})
        )
        adapter._get_ollama = MagicMock(return_value=MagicMock(status=lambda: {}))
        adapter._get_vllm = MagicMock(return_value=MagicMock(status=lambda: {}))
        adapter._get_litellm = MagicMock(return_value=MagicMock(status=lambda: {}))
        adapter._get_llama_cpp = MagicMock(return_value=MagicMock(status=lambda: {}))
        adapter._get_omniroute = MagicMock(return_value=MagicMock(status=lambda: {}))
        status = adapter.status()
        self.assertIn("resilience", status)
        self.assertTrue(status["resilience"]["enabled"])
        self.assertIn("openrouter", status)


if __name__ == "__main__":
    unittest.main()
