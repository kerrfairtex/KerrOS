"""Guard Docker event-mesh compose: loopback host ports + two nodes."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "event_mesh" / "docker-compose.yml"
DOCKERFILE = ROOT / "deploy" / "event_mesh" / "Dockerfile"
SCRIPT = ROOT / "scripts" / "event_mesh_docker.sh"
ENTRY = ROOT / "scripts" / "mesh_node.py"


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


class EventMeshComposeTest(unittest.TestCase):
    def test_artifacts_exist(self):
        self.assertTrue(COMPOSE.is_file())
        self.assertTrue(DOCKERFILE.is_file())
        self.assertTrue(SCRIPT.is_file())
        self.assertTrue(ENTRY.is_file())
        self.assertTrue(SCRIPT.read_text(encoding="utf-8").startswith("#!/"))

    def test_two_nodes_on_mesh_network(self):
        data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        services = data.get("services") or {}
        self.assertIn("node-a", services)
        self.assertIn("node-b", services)
        self.assertEqual(
            services["node-a"]["environment"]["KERROS_EVENT_MESH_HTTP_PEERS"],
            "http://node-b:8787/mesh/ingest",
        )
        self.assertEqual(
            services["node-b"]["environment"]["KERROS_EVENT_MESH_HTTP_PEERS"],
            "http://node-a:8787/mesh/ingest",
        )
        self.assertIn(
            "KERROS_EVENT_MESH_TOKEN",
            services["node-a"]["environment"],
        )
        self.assertIn("mesh", data.get("networks") or {})

    def test_all_host_ports_are_loopback(self):
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
            self.assertFalse(re.fullmatch(r"\d+:\d+", p), f"all-interfaces publish: {p}")

    def test_dockerfile_uses_mesh_node_entrypoint(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("scripts/mesh_node.py", text)
        self.assertIn("EXPOSE 8787", text)


if __name__ == "__main__":
    unittest.main()
