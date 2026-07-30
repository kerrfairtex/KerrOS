"""Phase A / ADR-050: offline profile + llama.cpp LLMPort."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adapters.llm.llama_cpp_adapter import LlamaCppAdapter, is_llama_cpp_enabled
from adapters.llm.offline_profile import (
    load_offline_profile,
    profile_gguf_path,
    resolve_profile_path,
)


class OfflineProfileTest(unittest.TestCase):
    def test_loads_bundled_offline_qwen05(self):
        profile = load_offline_profile("offline_qwen05")
        self.assertTrue(profile.get("ok"))
        self.assertEqual(profile.get("prompt_format"), "chatml")
        self.assertEqual(profile.get("runtime", {}).get("provider"), "llama_cpp")
        gguf = profile_gguf_path(profile)
        self.assertTrue(str(gguf).endswith("qwen0.5b-q4.gguf"))

    def test_resolve_path(self):
        path = resolve_profile_path("offline_qwen05")
        self.assertTrue(path.is_file())


class LlamaCppAdapterTest(unittest.TestCase):
    def test_unavailable_without_binary_or_model(self):
        adapter = LlamaCppAdapter(
            binary="/nonexistent/llama-cli",
            model_path="/nonexistent/model.gguf",
            server_endpoint="",
            profile={"name": "test", "prompt_format": "chatml"},
        )
        st = adapter.status()
        self.assertFalse(st["available"])
        out = adapter.complete("hi")
        self.assertIn("missing", out.lower())

    def test_chatml_subprocess_complete(self):
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "llama-fake"
            model = Path(td) / "qwen0.5b-q4.gguf"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)
            model.write_bytes(b"GGUF")
            gen = MagicMock()
            gen.generate.return_value = "hello offline"
            adapter = LlamaCppAdapter(
                binary=str(binary),
                model_path=str(model),
                server_endpoint="",
                profile={"name": "test", "prompt_format": "chatml"},
                generator=gen,
            )
            self.assertTrue(adapter.available())
            out = adapter.complete("ping", system="sys", history=[])
            self.assertEqual(out, "hello offline")
            prompt = gen.generate.call_args[0][0]
            self.assertIn("<|im_start|>system", prompt)
            self.assertIn("<|im_start|>user", prompt)
            self.assertIn("ping", prompt)

    def test_enabled_via_env(self):
        with patch.dict("os.environ", {"KERROS_OFFLINE_PROFILE": "offline_qwen05"}, clear=False):
            self.assertTrue(is_llama_cpp_enabled({}))


class CompositeLlamaCppTest(unittest.TestCase):
    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_cloud")
    @patch("adapters.llm.composite_adapter.CompositeLLMAdapter._get_llama_cpp")
    def test_provider_hint_llama_cpp(self, mock_get_llama, mock_get_cloud):
        from adapters.llm.composite_adapter import CompositeLLMAdapter

        local = MagicMock()
        local.status.return_value = {"available": True}
        local.complete.return_value = "from llama.cpp"
        mock_get_llama.return_value = local
        mock_get_cloud.return_value = MagicMock()

        adapter = CompositeLLMAdapter()
        result = adapter.complete("test", provider_hint="llama_cpp")
        self.assertEqual(result, "from llama.cpp")
        self.assertEqual(adapter.last_api_used(), "llama_cpp")


if __name__ == "__main__":
    unittest.main()
