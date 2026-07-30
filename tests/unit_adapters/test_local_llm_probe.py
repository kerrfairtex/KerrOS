"""Unit tests for Ollama / vLLM HTTP probes (C-19)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from adapters.llm.local_llm_probe import (
    is_ollama_enabled,
    is_vllm_enabled,
    probe_ollama,
    probe_vllm,
)

_CLEAR_ENV = {
    "KERROS_LOCAL_LLM": "",
    "KERROS_LLM_PROVIDER": "",
    "KERROS_OLLAMA_ENABLED": "",
    "KERROS_VLLM_ENABLED": "",
}


class LocalLLMProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, _CLEAR_ENV, clear=False)
        self._env.start()
        for k in _CLEAR_ENV:
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        self._env.stop()

    def test_enabled_flags(self):
        self.assertFalse(is_ollama_enabled({"ollama_enabled": False}))
        self.assertTrue(is_ollama_enabled({"ollama_enabled": True}))
        self.assertTrue(is_ollama_enabled({"local_llm": True}))
        self.assertTrue(is_vllm_enabled({"vllm_enabled": True}))
        self.assertTrue(is_vllm_enabled({"llm_provider_default": "vllm"}))

    @mock.patch("adapters.llm.local_llm_probe.requests.get")
    def test_probe_ollama_disabled_but_reachable(self, get):
        r = mock.Mock()
        r.status_code = 200
        r.json.return_value = {"data": [{"id": "llama3.2:latest"}]}
        get.return_value = r
        out = probe_ollama(
            "http://127.0.0.1:11434/v1",
            config={"ollama_enabled": False, "local_llm": False},
        )
        self.assertFalse(out["enabled"])
        self.assertEqual(out["status"], "disabled")
        self.assertTrue(out["available"])
        self.assertEqual(out["models"], 1)
        self.assertTrue(get.call_args[0][0].endswith("/models"))

    @mock.patch("adapters.llm.local_llm_probe.requests.get")
    def test_probe_ollama_enabled_ok(self, get):
        r = mock.Mock()
        r.status_code = 200
        r.json.return_value = {"data": [{"id": "m1"}, {"id": "m2"}]}
        get.return_value = r
        out = probe_ollama(
            "http://127.0.0.1:11434/v1",
            config={"ollama_enabled": True},
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["models"], 2)

    @mock.patch("adapters.llm.local_llm_probe.requests.get")
    def test_probe_ollama_enabled_unreachable(self, get):
        get.side_effect = ConnectionError("refused")
        out = probe_ollama(
            "http://127.0.0.1:11434/v1",
            config={"ollama_enabled": True},
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["status"], "unavailable")
        self.assertIn("refused", out["error"])

    @mock.patch("adapters.llm.local_llm_probe.requests.get")
    def test_probe_vllm_enabled_ok(self, get):
        r = mock.Mock()
        r.status_code = 200
        r.json.return_value = {"data": [{"id": "meta-llama/Llama-3.2-3B-Instruct"}]}
        get.return_value = r
        out = probe_vllm(
            "http://127.0.0.1:8000/v1",
            config={"vllm_enabled": True},
        )
        self.assertTrue(out["enabled"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["models"], 1)

    @mock.patch("adapters.llm.local_llm_probe.requests.get")
    def test_probe_vllm_http_error(self, get):
        r = mock.Mock()
        r.status_code = 503
        r.json.return_value = {}
        get.return_value = r
        out = probe_vllm(
            "http://127.0.0.1:8000/v1",
            config={"vllm_enabled": True},
        )
        self.assertEqual(out["status"], "unavailable")
        self.assertIn("503", out["error"])


if __name__ == "__main__":
    unittest.main()
