"""Guard OmniRoute droplet compose: host ports must stay loopback-only."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "omniroute" / "docker-compose.yml"
SCRIPT = ROOT / "scripts" / "omniroute_droplet.sh"


def _published_ports(compose_text: str) -> list[str]:
    data = yaml.safe_load(compose_text)
    ports: list[str] = []
    for svc in (data.get("services") or {}).values():
        for entry in svc.get("ports") or []:
            if isinstance(entry, str):
                ports.append(entry)
            elif isinstance(entry, dict) and "published" in entry:
                published = entry["published"]
                target = entry.get("target", "")
                ip = entry.get("host_ip", "0.0.0.0")
                ports.append(f"{ip}:{published}:{target}")
    return ports


class OmniRouteComposeTest(unittest.TestCase):
    def test_compose_file_exists(self):
        self.assertTrue(COMPOSE.is_file(), f"missing {COMPOSE}")

    def test_script_exists_and_executable_bit(self):
        self.assertTrue(SCRIPT.is_file())
        # Executable bit may vary on checkout; script must have shebang.
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/"))

    def test_all_host_ports_are_loopback(self):
        text = COMPOSE.read_text(encoding="utf-8")
        ports = _published_ports(text)
        self.assertTrue(ports, "expected at least one published port")
        for p in ports:
            self.assertTrue(
                p.startswith("127.0.0.1:") or p.startswith("localhost:") or p.startswith("::1:"),
                f"non-loopback publish: {p}",
            )
            # Reject bare "20128:20128" style (would appear without IP prefix).
            self.assertFalse(re.fullmatch(r"\d+:\d+", p), f"all-interfaces publish: {p}")

    def test_default_image_is_pinned(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn("diegosouzapw/omniroute:3.8.49", text)
        self.assertNotIn("omniroute:latest", text)

    def test_env_example_documents_kerros_endpoint(self):
        env_ex = ROOT / "deploy" / "omniroute" / ".env.example"
        body = env_ex.read_text(encoding="utf-8")
        self.assertIn("OMNIROUTE_ENDPOINT", body)
        self.assertIn("127.0.0.1:20128", body)


if __name__ == "__main__":
    unittest.main()
