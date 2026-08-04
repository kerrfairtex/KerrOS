"""OpenRouter setup + CompositeLLMAdapter free-first hop."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml


class OpenRouterSetupTest(unittest.TestCase):
    def test_tiers_yaml_parses_and_has_chat_primary(self):
        root = Path(__file__).resolve().parents[2]
        path = root / "config" / "openrouter_tiers.yaml"
        self.assertTrue(path.is_file())
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertIn("tiers", data)
        chat = data["tiers"]["chat"]
        self.assertTrue(any(m.get("id", "").endswith(":free") for m in chat))
        self.assertTrue(
            any(m.get("id") == "inclusionai/ling-3.0-flash:free" for m in chat)
        )
        # Live public slugs (regression: old short names 404)
        self.assertEqual(
            data["tiers"]["research"][0]["id"], "poolside/laguna-s-2.1:free"
        )
        self.assertTrue(
            any(
                m.get("id") == "nvidia/nemotron-3-ultra-550b-a55b:free"
                for m in data["tiers"]["reasoning"]
            )
        )
        self.assertTrue(
            any(m.get("id") == "google/gemma-4-26b-a4b-it:free" for m in chat)
        )
        self.assertEqual(
            data["tiers"]["coding"][0]["id"], "cohere/north-mini-code:free"
        )
        # Panel routers stay off the free path
        for entry in data["tiers"]["routers"]:
            self.assertFalse(entry.get("free"), entry)
        self.assertFalse(data["tiers"]["paid"][0]["free"])
        self.assertEqual(data["tiers"]["paid"][0]["id"], "google/gemini-3.5-flash-lite")

    def test_adapter_unavailable_without_key(self):
        from adapters.llm.openrouter_adapter import OpenRouterAdapter

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
            a = OpenRouterAdapter(api_key="")
            self.assertFalse(a.available())
            st = a.status()
            self.assertFalse(st["available"])
            self.assertIn("OPENROUTER_API_KEY", st.get("setup_hint") or "")
            out = a.complete("hi")
            self.assertTrue(out.startswith("[openrouter]"))

    def test_adapter_uses_tier_candidates(self):
        from adapters.llm.openrouter_adapter import OpenRouterAdapter

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "tiers.yaml"
            cfg.write_text(
                yaml.dump(
                    {
                        "tiers": {
                            "chat": [
                                {"id": "test/model:free", "free": True},
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            a = OpenRouterAdapter(api_key="sk-or-test", config_path=cfg)
            with patch.object(a, "_post", return_value=("hello", None)) as post:
                out = a.complete("hi", tier="chat")
            self.assertEqual(out, "hello")
            post.assert_called_once()
            self.assertEqual(post.call_args[0][0], "test/model:free")
            self.assertEqual(a.last_api_used(), "test/model:free")

    def test_composite_tries_openrouter_before_cloud(self):
        from adapters.llm.composite_adapter import CompositeLLMAdapter

        adapter = CompositeLLMAdapter()
        or_mock = MagicMock()
        or_mock.status.return_value = {"available": True}
        or_mock.complete.return_value = "from openrouter"
        cloud = MagicMock()
        cloud.complete.return_value = "from cloud"
        adapter._get_openrouter = MagicMock(return_value=or_mock)
        adapter._get_cloud = MagicMock(return_value=cloud)

        out = adapter.complete("hi")
        self.assertEqual(out, "from openrouter")
        self.assertEqual(adapter.last_api_used(), "openrouter")
        cloud.complete.assert_not_called()

    def test_composite_skips_openrouter_without_key(self):
        from adapters.llm.composite_adapter import CompositeLLMAdapter

        adapter = CompositeLLMAdapter()
        or_mock = MagicMock()
        or_mock.status.return_value = {
            "available": False,
            "setup_hint": "Set OPENROUTER_API_KEY",
        }
        cloud = MagicMock()
        cloud.status.return_value = {"openrouter": False}
        cloud.complete.return_value = "from cloud"
        adapter._get_openrouter = MagicMock(return_value=or_mock)
        adapter._get_cloud = MagicMock(return_value=cloud)

        out = adapter.complete("hi")
        self.assertEqual(out, "from cloud")
        or_mock.complete.assert_not_called()

    def test_openrouter_soft_fail_falls_through(self):
        from adapters.llm.composite_adapter import CompositeLLMAdapter
        from adapters.llm.resilience import looks_like_provider_failure

        self.assertTrue(
            looks_like_provider_failure("[openrouter] all candidates in tier 'chat' failed")
        )
        adapter = CompositeLLMAdapter()
        or_mock = MagicMock()
        or_mock.status.return_value = {"available": True}
        or_mock.complete.return_value = "[openrouter] all candidates failed"
        cloud = MagicMock()
        cloud.complete.return_value = "from cloud"
        adapter._get_openrouter = MagicMock(return_value=or_mock)
        adapter._get_cloud = MagicMock(return_value=cloud)
        out = adapter.complete("hi")
        self.assertEqual(out, "from cloud")


if __name__ == "__main__":
    unittest.main()
