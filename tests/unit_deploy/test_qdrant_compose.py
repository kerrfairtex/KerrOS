"""Guard Qdrant compose: loopback host ports (C-18)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "qdrant" / "docker-compose.yml"
SCRIPT = ROOT / "scripts" / "qdrant_docker.sh"
MIGRATE = ROOT / "scripts" / "migrate_sqlite_rag_to_qdrant.py"


def _published_ports(compose_text: str) -> list[str]:
    data = yaml.safe_load(compose_text)
    ports: list[str] = []
    for svc in (data.get("services") or {}).values():
        for entry in svc.get("ports") or []:
            if isinstance(entry, str):
                ports.append(entry)
    return ports


class QdrantComposeTest(unittest.TestCase):
    def test_artifacts_exist(self):
        self.assertTrue(COMPOSE.is_file())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(MIGRATE.is_file())
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/"))

    def test_loopback_ports_and_pinned_image(self):
        text = COMPOSE.read_text(encoding="utf-8")
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
        self.assertIn("qdrant/qdrant:v1.13.2", text)
        self.assertIn("kerros-qdrant-data", text)


if __name__ == "__main__":
    unittest.main()
