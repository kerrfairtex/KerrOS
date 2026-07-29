"""Event mesh transport tests — durable broker + peer discovery (ADR-009)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.event_bus import EventBus
from runtime.event_mesh import LocalEventMesh, build_event_mesh
from runtime.event_mesh_broker import (
    DurableEventBroker,
    DurableEventMeshTransport,
    FilePeerRegistry,
)


class FilePeerRegistryTest(unittest.TestCase):
    def test_announce_and_list_peers(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            a = FilePeerRegistry(directory=directory, node_id="a", ttl_s=60)
            b = FilePeerRegistry(directory=directory, node_id="b", ttl_s=60)
            a.announce({"role": "primary"})
            b.announce({})
            peers = a.peers()
            self.assertEqual(len(peers), 1)
            self.assertEqual(peers[0].node_id, "b")
            b.close()
            # TTL still sees file until unlink — close removes b's heartbeat.
            self.assertEqual(a.peers(), [])


class DurableBrokerTest(unittest.TestCase):
    def test_publish_drain_ack_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "broker.db"
            broker_a = DurableEventBroker(db_path=db, node_id="node-a")
            broker_b = DurableEventBroker(db_path=db, node_id="node-b")
            bus_a = EventBus()
            bus_b = EventBus()
            mesh_a = LocalEventMesh(
                node_id="node-a",
                buses=[bus_a],
                transport=DurableEventMeshTransport(broker=broker_a),
            )
            mesh_b = LocalEventMesh(
                node_id="node-b",
                buses=[bus_b],
                transport=DurableEventMeshTransport(broker=broker_b),
            )
            mesh_a.attach()
            mesh_b.attach()

            seen = []
            bus_b.subscribe("durable.evt", lambda e: seen.append(e.payload))
            bus_a.publish("durable.evt", {"n": 7})

            self.assertEqual(mesh_b.poll_durable_transport(), 1)
            self.assertEqual(seen, [{"n": 7}])
            # Already acked — second poll is empty.
            self.assertEqual(mesh_b.poll_durable_transport(), 0)

            mesh_a.detach()
            mesh_b.detach()

    def test_at_least_once_until_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "broker.db"
            broker_a = DurableEventBroker(db_path=db, node_id="a")
            broker_b = DurableEventBroker(db_path=db, node_id="b")
            from runtime.event_bus import Event

            event = Event(topic="x", payload={"k": 1}, source="a")
            self.assertTrue(broker_a.publish(event, origin_node="a"))
            pending = broker_b.drain_pending()
            self.assertEqual(len(pending), 1)
            # Without ack, still pending.
            self.assertEqual(broker_b.pending_count(), 1)
            broker_b.ack(event.id)
            self.assertEqual(broker_b.pending_count(), 0)

    def test_peer_heartbeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "broker.db"
            a = DurableEventBroker(db_path=db, node_id="a", peer_ttl_s=60)
            b = DurableEventBroker(db_path=db, node_id="b", peer_ttl_s=60)
            a.announce({"v": 1})
            b.announce({"v": 2})
            peers = a.peers()
            self.assertEqual([p.node_id for p in peers], ["b"])

    def test_build_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            bus = EventBus()
            mesh = build_event_mesh(
                bus,
                cfg={
                    "enabled": True,
                    "node_id": "n1",
                    "transport": "durable",
                    "broker_db": "broker.db",
                    "discovery_dir": "peers",
                },
                base=base,
            )
            self.assertIsNotNone(mesh)
            self.assertEqual(mesh.stats()["transport"], "DurableEventMeshTransport")
            self.assertIsNotNone(mesh.discovery)
            mesh.heartbeat()
            # Self is excluded from peers().
            self.assertEqual(mesh.peers(), [])
            mesh.detach()


class MeshPollAliasTest(unittest.TestCase):
    def test_poll_dispatches_to_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "broker.db"
            ta = DurableEventMeshTransport(
                broker=DurableEventBroker(db_path=db, node_id="a")
            )
            tb = DurableEventMeshTransport(
                broker=DurableEventBroker(db_path=db, node_id="b")
            )
            ma = LocalEventMesh(node_id="a", buses=[EventBus()], transport=ta)
            mb = LocalEventMesh(node_id="b", buses=[EventBus()], transport=tb)
            ma.attach()
            mb.attach()
            seen = []
            mb.buses[0].subscribe("p", lambda e: seen.append(1))
            ma.publish_local("p", {})
            self.assertEqual(mb.poll(), 1)
            self.assertEqual(seen, [1])
            ma.detach()
            mb.detach()


if __name__ == "__main__":
    unittest.main()
