"""ADR-055 adaptive integrations catalog."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class AdaptiveIntegrationsTest(unittest.TestCase):
    def test_api_config_has_coding_tier_and_frameworks(self):
        from adapters.integrations.registry import load_registry, list_tiers

        cfg = load_registry(ROOT / "api_config.yaml")
        self.assertIn("crewai", (cfg.get("agent_frameworks") or {}))
        self.assertIn("autogen", (cfg.get("agent_frameworks") or {}))
        self.assertIn("elicit", (cfg.get("search_and_research") or {}))
        self.assertIn("openalex", (cfg.get("search_and_research") or {}))
        self.assertIn("jenni", (cfg.get("academic_writing") or {}))
        self.assertIn("tabnine", (cfg.get("coding_agents") or {}))
        tiers = list_tiers(cfg)
        self.assertIn("coding", tiers)
        self.assertIn("research", tiers)
        self.assertIn("sol", tiers)
        providers = tiers["coding"]["providers"]
        self.assertIn("deepseek", providers)
        self.assertIn("anthropic", providers)

    def test_preferred_coding_models(self):
        from adapters.integrations.registry import load_registry

        cloud = (load_registry().get("llm_cloud") or {})
        self.assertEqual(cloud["anthropic"]["model"], "claude-opus-4-7")
        self.assertEqual(cloud["openai"]["model"], "gpt-5.2")
        self.assertEqual(cloud["deepseek"]["model"], "deepseek-reasoner")

    def test_resolve_tier_picks_configured_provider(self):
        from adapters.integrations.registry import resolve_tier

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test-deepseek"}, clear=False):
            hit = resolve_tier("coding")
        self.assertTrue(hit["ok"])
        self.assertEqual(hit["provider"], "deepseek")

    def test_catalog_status_never_leaks_secret(self):
        from adapters.integrations.registry import catalog_status, format_status_lines

        with patch.dict(os.environ, {"GROQ_API_KEY": "super-secret-value-xyz"}, clear=False):
            st = catalog_status(sections=["llm_cloud"])
            blob = "\n".join(format_status_lines(st, section="llm_cloud", ready_only=True))
        self.assertNotIn("super-secret-value-xyz", blob)
        self.assertIn("GROQ_API_KEY", blob)

    def test_adr_and_capability_manifest_exist(self):
        self.assertTrue((ROOT / "docs/adr/ADR-055-adaptive-integrations-catalog.md").is_file())
        self.assertTrue((ROOT / "config/capabilities/adaptive_integrations.yaml").is_file())

    def test_env_example_has_crewai_slot(self):
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("CREWAI_API_KEY=", text)
        self.assertIn("KERROS_ROUTING_TIER=", text)
        self.assertIn("ASI_ONE_API_KEY=", text)


if __name__ == "__main__":
    unittest.main()
