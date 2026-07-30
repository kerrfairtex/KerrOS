"""Guard Ollama compose: loopback host ports (C-19 / ADR-016 / ADR-049)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "ollama" / "docker-compose.yml"
README = ROOT / "deploy" / "ollama" / "README.md"
SCRIPT = ROOT / "scripts" / "local_llm_docker.sh"
ADR = ROOT / "docs" / "adr" / "ADR-016-local-llm-ops.md"
PROXY = ROOT / "deploy" / "ollama" / "proxy" / "Caddyfile"


def _published_ports(compose_text: str) -> list[str]:
    data = yaml.safe_load(compose_text)
    ports: list[str] = []
    for svc in (data.get("services") or {}).values():
        for entry in svc.get("ports") or []:
            if isinstance(entry, str):
                ports.append(entry)
    return ports


class OllamaComposeTest(unittest.TestCase):
    def test_artifacts_exist(self):
        self.assertTrue(COMPOSE.is_file())
        self.assertTrue(README.is_file())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(ADR.is_file())
        self.assertTrue(PROXY.is_file())
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/"))
        self.assertIn("C-19", ADR.read_text(encoding="utf-8"))

    def test_loopback_ports_and_pinned_image(self):
        text = COMPOSE.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        services = data.get("services") or {}
        self.assertIn("ollama", services)
        self.assertIn("llm-proxy", services)
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
        self.assertIn("ollama/ollama:", text)
        self.assertIn("kerros-ollama-data", text)
        self.assertIn("OLLAMA_HOST", text)


if __name__ == "__main__":
    unittest.main()
