"""Event mesh foundation tests (P3 / C-16 seam)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.event_bus import Event, EventBus
from runtime.event_mesh import (
    FileEventMeshTransport,
    HttpEventMeshTransport,
    LocalEventMesh,
    NullEventMeshTransport,
    build_event_mesh,
)
from kernel.boot import boot, shutdown


class EventRoundTripTest(unittest.TestCase):
    def test_from_dict_preserves_identity(self):
        original = Event(topic="a.b", payload={"x": 1}, source="t")
        cloned = Event.from_dict(original.to_dict())
        self.assertEqual(cloned.id, original.id)
        self.assertEqual(cloned.topic, "a.b")
        self.assertEqual(cloned.payload, {"x": 1})
        self.assertEqual(cloned.source, "t")


class LocalEventMeshTest(unittest.TestCase):
    def test_fanout_between_buses_no_loop(self):
        a = EventBus()
        b = EventBus()
        seen_a = []
        seen_b = []
        a.subscribe("mesh.ping", lambda e: seen_a.append(e.id))
        b.subscribe("mesh.ping", lambda e: seen_b.append(e.id))

        mesh = LocalEventMesh(node_id="n1", buses=[a, b], transport=NullEventMeshTransport())
        mesh.attach()
        event = a.publish("mesh.ping", {"ok": True}, source="test")
        self.assertEqual(seen_a, [event.id])
        self.assertEqual(seen_b, [event.id])
        self.assertEqual(mesh.stats()["forwarded"], 1)
        mesh.detach()

    def test_null_transport_records_send(self):
        bus = EventBus()
        transport = NullEventMeshTransport()
        mesh = LocalEventMesh(node_id="n1", buses=[bus], transport=transport)
        mesh.attach()
        bus.publish("x", {"n": 1})
        self.assertEqual(len(transport.sent), 1)
        self.assertEqual(transport.sent[0].topic, "x")
        mesh.detach()

    def test_file_transport_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            a = EventBus()
            b = EventBus()
            ta = FileEventMeshTransport(directory=directory, node_id="node-a")
            tb = FileEventMeshTransport(directory=directory, node_id="node-b")
            mesh_a = LocalEventMesh(node_id="node-a", buses=[a], transport=ta)
            mesh_b = LocalEventMesh(node_id="node-b", buses=[b], transport=tb)
            mesh_a.attach()
            mesh_b.attach()

            seen = []
            b.subscribe("file.evt", lambda e: seen.append(e.payload))
            a.publish("file.evt", {"v": 42})
            # B drains A's file
            count = mesh_b.poll_file_transport()
            self.assertEqual(count, 1)
            self.assertEqual(seen, [{"v": 42}])
            mesh_a.detach()
            mesh_b.detach()

    def test_http_stub_posts_without_peers(self):
        transport = HttpEventMeshTransport(peers=[])
        mesh = LocalEventMesh(
            node_id="n1", buses=[EventBus()], transport=transport
        )
        mesh.attach()
        mesh.publish_local("http.evt", {"a": 1})
        self.assertEqual(len(transport.posted), 1)
        mesh.detach()

    def test_build_disabled_by_default(self):
        bus = EventBus()
        self.assertIsNone(build_event_mesh(bus, cfg={"enabled": False}))

    def test_build_enabled_null(self):
        bus = EventBus()
        mesh = build_event_mesh(
            bus, cfg={"enabled": True, "node_id": "t", "transport": "null"}
        )
        self.assertIsNotNone(mesh)
        self.assertEqual(mesh.node_id, "t")
        mesh.detach()


class BootEventMeshTest(unittest.TestCase):
    def tearDown(self):
        shutdown()

    def test_boot_without_mesh_by_default(self):
        shutdown()
        boot()
        from kernel import resolve
        from kernel.contract import SERVICE_EVENT_MESH

        # has() may not exist — try resolve
        from kernel.boot import get_kernel

        k = get_kernel()
        self.assertFalse(k.container.has(SERVICE_EVENT_MESH))
        shutdown()


if __name__ == "__main__":
    unittest.main()
