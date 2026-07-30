"""Health wiring for optional Ollama / vLLM (C-19)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from kernel.boot import boot, shutdown
from runtime.health import HealthMonitor


class LocalLLMHealthTest(unittest.TestCase):
    @patch("adapters.memory.qdrant_vector_store.probe_qdrant")
    @patch("adapters.llm.omniroute_adapter.probe_omniroute")
    @patch("adapters.llm.local_llm_probe.probe_vllm")
    @patch("adapters.llm.local_llm_probe.probe_ollama")
    def test_ollama_fail_fails_overall_when_enabled(
        self, mock_ollama, mock_vllm, mock_omni, mock_qdrant
    ):
        shutdown()
        boot()
        mock_omni.return_value = {
            "provider": "omniroute",
            "enabled": False,
            "status": "disabled",
        }
        mock_qdrant.return_value = {
            "component": "qdrant",
            "enabled": False,
            "status": "disabled",
        }
        mock_vllm.return_value = {
            "provider": "vllm",
            "enabled": False,
            "status": "disabled",
        }
        mock_ollama.return_value = {
            "provider": "ollama",
            "enabled": True,
            "base_url": "http://127.0.0.1:11434/v1",
            "available": False,
            "status": "unavailable",
            "error": "refused",
        }
        try:
            report = HealthMonitor().collect()
            self.assertFalse(report["healthy"])
            self.assertEqual(report["components"]["ollama"]["status"], "unavailable")
        finally:
            shutdown()

    @patch("adapters.memory.qdrant_vector_store.probe_qdrant")
    @patch("adapters.llm.omniroute_adapter.probe_omniroute")
    @patch("adapters.llm.local_llm_probe.probe_vllm")
    @patch("adapters.llm.local_llm_probe.probe_ollama")
    def test_disabled_local_llm_does_not_fail_health(
        self, mock_ollama, mock_vllm, mock_omni, mock_qdrant
    ):
        shutdown()
        boot()
        mock_omni.return_value = {
            "provider": "omniroute",
            "enabled": False,
            "status": "disabled",
        }
        mock_qdrant.return_value = {
            "component": "qdrant",
            "enabled": False,
            "status": "disabled",
        }
        mock_ollama.return_value = {
            "provider": "ollama",
            "enabled": False,
            "status": "disabled",
            "available": False,
        }
        mock_vllm.return_value = {
            "provider": "vllm",
            "enabled": False,
            "status": "disabled",
            "available": False,
        }
        try:
            report = HealthMonitor().collect()
            self.assertTrue(report["healthy"])
            self.assertEqual(report["components"]["ollama"]["status"], "disabled")
            self.assertEqual(report["components"]["vllm"]["status"], "disabled")
        finally:
            shutdown()


if __name__ == "__main__":
    unittest.main()
