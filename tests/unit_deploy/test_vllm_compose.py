"""Guard vLLM compose: loopback host ports + profiles (C-19 / ADR-048 / ADR-049)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "vllm" / "docker-compose.yml"
README = ROOT / "deploy" / "vllm" / "README.md"
SCRIPT = ROOT / "scripts" / "vllm_docker.sh"
ADR = ROOT / "docs" / "adr" / "ADR-048-vllm-ops-kit.md"
ADR049 = ROOT / "docs" / "adr" / "ADR-049-local-llm-residuals.md"
ENV = ROOT / "deploy" / "vllm" / ".env.example"
PROXY = ROOT / "deploy" / "vllm" / "proxy" / "Caddyfile"


def _published_ports(compose_text: str) -> list[str]:
    data = yaml.safe_load(compose_text)
    ports: list[str] = []
    for svc in (data.get("services") or {}).values():
        for entry in svc.get("ports") or []:
            if isinstance(entry, str):
                ports.append(entry)
    return ports


class VllmComposeTest(unittest.TestCase):
    def test_artifacts_exist(self):
        self.assertTrue(COMPOSE.is_file())
        self.assertTrue(README.is_file())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(ADR.is_file())
        self.assertTrue(ADR049.is_file())
        self.assertTrue(ENV.is_file())
        self.assertTrue(PROXY.is_file())
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/"))
        self.assertIn("ADR-048", ADR.read_text(encoding="utf-8"))
        self.assertIn("ADR-049", ADR049.read_text(encoding="utf-8"))

    def test_loopback_ports_profiles_and_pinned_image(self):
        text = COMPOSE.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        services = data.get("services") or {}
        self.assertIn("vllm", services)
        self.assertIn("vllm-cpu", services)
        self.assertIn("llm-proxy", services)
        self.assertIn("vllm-node-a", services)
        self.assertIn("vllm-node-b", services)
        self.assertIn("vllm", services["vllm"].get("profiles") or [])
        self.assertIn("cpu", services["vllm-cpu"].get("profiles") or [])
        self.assertIn("proxy", services["llm-proxy"].get("profiles") or [])
        self.assertIn("multi", services["vllm-node-a"].get("profiles") or [])
        self.assertIn("multi", services["vllm-node-b"].get("profiles") or [])
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
        self.assertIn("vllm/vllm-openai:", text)
        self.assertIn("kerros-vllm-cache", text)
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("check_loopback", script)
        self.assertIn("--profile", script)
        self.assertIn("--proxy", script)
        self.assertIn("--multi", script)


if __name__ == "__main__":
    unittest.main()
