"""HTTP event-mesh ingest server tests (ADR-011)."""

from __future__ import annotations

import json
import time
import unittest
import urllib.error
import urllib.request

from runtime.event_bus import EventBus
from runtime.event_mesh import HttpEventMeshTransport, LocalEventMesh, build_event_mesh
from runtime.event_mesh_http import parse_listen_addr, start_mesh_http_server


class ParseListenAddrTest(unittest.TestCase):
    def test_port_only(self):
        self.assertEqual(parse_listen_addr("8787"), ("0.0.0.0", 8787))

    def test_host_port(self):
        self.assertEqual(parse_listen_addr("127.0.0.1:9001"), ("127.0.0.1", 9001))


class EventMeshHttpServerTest(unittest.TestCase):
    def test_ingest_and_publish_round_trip(self):
        bus_a = EventBus()
        bus_b = EventBus()
        # Start B first so A can point peers at B's ephemeral port.
        mesh_b = LocalEventMesh(
            node_id="b",
            buses=[bus_b],
            transport=HttpEventMeshTransport(peers=[]),
        )
        mesh_b.attach()
        server_b = start_mesh_http_server(mesh_b, listen="127.0.0.1:0")
        mesh_b.http_server = server_b

        mesh_a = LocalEventMesh(
            node_id="a",
            buses=[bus_a],
            transport=HttpEventMeshTransport(peers=[server_b.url_ingest]),
        )
        mesh_a.attach()
        server_a = start_mesh_http_server(mesh_a, listen="127.0.0.1:0")
        mesh_a.http_server = server_a

        seen = []
        bus_b.subscribe("http.mesh", lambda e: seen.append(e.payload))

        # Publish via A's HTTP API → transport POST → B ingest.
        body = json.dumps(
            {"topic": "http.mesh", "payload": {"n": 1}}
        ).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{server_a.port}/mesh/publish",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            pub = json.loads(resp.read().decode())
        self.assertTrue(pub.get("ok"))

        deadline = time.time() + 3
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(seen, [{"n": 1}])
        self.assertGreaterEqual(mesh_b.stats()["ingested"], 1)

        with urllib.request.urlopen(server_b.url_health, timeout=2) as resp:
            health = json.loads(resp.read().decode())
        self.assertTrue(health["ok"])
        self.assertEqual(health["node_id"], "b")

        mesh_a.detach()
        mesh_b.detach()

    def test_build_starts_listener_when_configured(self):
        bus = EventBus()
        mesh = build_event_mesh(
            bus,
            cfg={
                "enabled": True,
                "node_id": "listen-test",
                "transport": "http",
                "http_peers": [],
                "http_listen": "127.0.0.1:0",
            },
        )
        self.assertIsNotNone(mesh)
        self.assertIsNotNone(mesh.http_server)
        self.assertGreater(mesh.http_server.port, 0)
        mesh.detach()


if __name__ == "__main__":
    unittest.main()
