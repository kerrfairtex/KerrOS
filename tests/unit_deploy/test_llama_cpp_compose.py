"""Guard llama.cpp + LiteLLM compose (Phase E / ADR-054)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "llama_cpp" / "docker-compose.yml"
README = ROOT / "deploy" / "llama_cpp" / "README.md"
SCRIPT = ROOT / "scripts" / "llama_cpp_docker.sh"
ADR = ROOT / "docs" / "adr" / "ADR-054-offline-litellm-llamacpp.md"
ENV = ROOT / "deploy" / "llama_cpp" / ".env.example"
LITELLM_CFG = ROOT / "deploy" / "llama_cpp" / "litellm_config.yaml"
PROXY = ROOT / "deploy" / "llama_cpp" / "proxy" / "Caddyfile"


def _published_ports(compose_text: str) -> list[str]:
    data = yaml.safe_load(compose_text)
    ports: list[str] = []
    for svc in (data.get("services") or {}).values():
        for entry in svc.get("ports") or []:
            if isinstance(entry, str):
                ports.append(entry)
    return ports


class LlamaCppComposeTest(unittest.TestCase):
    def test_artifacts_exist(self):
        self.assertTrue(COMPOSE.is_file())
        self.assertTrue(README.is_file())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(ADR.is_file())
        self.assertTrue(ENV.is_file())
        self.assertTrue(LITELLM_CFG.is_file())
        self.assertTrue(PROXY.is_file())
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/"))
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("ADR-054", adr)
        self.assertIn("Pending — until live containers", adr)
        self.assertIn("not live", README.read_text(encoding="utf-8").lower())

    def test_loopback_ports_profiles_and_pinned_images(self):
        text = COMPOSE.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        services = data.get("services") or {}
        self.assertIn("llama-cpp", services)
        self.assertIn("litellm", services)
        self.assertIn("llm-proxy", services)
        self.assertIn("llama_cpp", services["llama-cpp"].get("profiles") or [])
        self.assertIn("litellm", services["litellm"].get("profiles") or [])
        self.assertIn("proxy", services["llm-proxy"].get("profiles") or [])
        ports = _published_ports(text)
        self.assertTrue(ports)
        for p in ports:
            self.assertTrue(
                p.startswith("127.0.0.1:")
                or p.startswith("localhost:")
                or p.startswith("::1:"),
                f"non-loopback publish: {p}",
            )
            self.assertFalse(re.fullmatch(r"\d+:\d+", p))
        self.assertIn("llama.cpp", text)
        self.assertIn("litellm", text)
        self.assertIn("kerros-offline-llm", text)
        litellm_cfg = LITELLM_CFG.read_text(encoding="utf-8")
        self.assertIn("qwen0.5b-q4", litellm_cfg)
        self.assertIn("llama-cpp:8080", litellm_cfg)
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("check_loopback", script)
        self.assertIn("--litellm", script)


class OfflineGatewayTest(unittest.TestCase):
    def test_fake_plan_never_production(self):
        from adapters.llm.offline_gateway import (
            OfflineGatewayConfig,
            OfflineGatewayPlanner,
            build_offline_gateway,
        )

        self.assertIsNone(build_offline_gateway({}))
        planner = OfflineGatewayPlanner(cfg=OfflineGatewayConfig(enabled=True))
        out = planner.plan()
        self.assertTrue(out["ok"])
        self.assertTrue(out["loopback"])
        self.assertFalse(out["production_gateway"])
        self.assertIn("LITELLM_ENDPOINT", out["client_env"])


if __name__ == "__main__":
    unittest.main()
