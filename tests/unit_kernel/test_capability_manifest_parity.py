"""Parity checks: manifests cover claw, scope_policy, and multi_api surfaces."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml

from kernel.boot import boot, resolve, shutdown
from scripts.render_capabilities import load_capabilities
from tools.registry import TOOL_DEFINITIONS

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "config" / "capabilities"
SCOPE_POLICY = ROOT / "config" / "scope_policy.yaml"


def _manifest_names() -> set[str]:
    return {c["name"] for c in load_capabilities(MANIFEST_DIR)}


class CapabilityManifestParityTest(unittest.TestCase):
    def test_claw_tools_in_manifests(self):
        names = _manifest_names()
        for tool in TOOL_DEFINITIONS:
            fn = tool.get("function", {})
            name = fn.get("name")
            self.assertTrue(name, "TOOL_DEFINITIONS entry missing name")
            self.assertIn(
                f"tool:{name}",
                names,
                f"claw tool {name!r} missing from capability YAML",
            )

    def test_scope_offensive_and_deploy_in_manifests(self):
        policy = yaml.safe_load(SCOPE_POLICY.read_text(encoding="utf-8")) or {}
        names = _manifest_names()
        for tool in policy.get("offensive_tools") or []:
            self.assertIn(f"tool:{tool}", names, f"offensive tool {tool!r} missing")
        for tool in policy.get("deploy_tools") or []:
            self.assertIn(f"tool:{tool}", names, f"deploy tool {tool!r} missing")

    def test_multi_api_status_keys_have_providers(self):
        # Keys from MultiAPIEngine.status() — each should be a provider:* entry
        # (litellm is shared with the dedicated litellm adapter).
        status_keys = (
            "groq",
            "nvidia",
            "deepseek",
            "kimi",
            "hunyuan",
            "cohere",
            "huggingface",
            "openrouter",
            "anthropic",
            "gemini",
            "litellm",
        )
        names = _manifest_names()
        for key in status_keys:
            self.assertIn(f"provider:{key}", names, f"multi_api provider {key!r} missing")
        self.assertIn("provider:composite", names)
        self.assertIn("provider:omniroute", names)

    def test_ports_and_devops_agent_present(self):
        names = _manifest_names()
        for port in ("llm", "memory", "tool", "dispatch", "search", "storage"):
            self.assertIn(f"port:{port}", names)
        self.assertIn("agent:devops", names)
        self.assertIn("tool:github_open_pr", names)
        self.assertIn("tool:calc", names)

    def test_boot_registry_includes_expanded_set(self):
        shutdown()
        os.environ["KERROS_WORKSPACE"] = tempfile.mkdtemp()
        try:
            boot()
            registry = resolve("capability_registry")
            names = {c.name for c in registry.list()}
            self.assertIn("tool:read", names)
            self.assertIn("tool:nmap", names)
            self.assertIn("provider:anthropic", names)
            self.assertIn("port:llm", names)
            tools = registry.list(kind="tool")
            self.assertGreaterEqual(len(tools), 30)
            providers = registry.list(kind="provider")
            self.assertGreaterEqual(len(providers), 12)
        finally:
            shutdown()


if __name__ == "__main__":
    unittest.main()
