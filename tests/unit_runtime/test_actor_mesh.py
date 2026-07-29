"""IPC actor-mesh tests (C-16 / ADR-012)."""

from __future__ import annotations

import socket
import time
import unittest

from runtime.actor_mesh import (
    ActorMesh,
    ActorMessage,
    NngActorBackend,
    SocketActorBackend,
    build_actor_mesh,
    format_tcp_url,
    nng_available,
    parse_tcp_url,
)
from runtime.service_bus import ServiceBus
from kernel.boot import boot, shutdown


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ParseTcpUrlTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_tcp_url("tcp://127.0.0.1:9091"), ("127.0.0.1", 9091))
        self.assertEqual(parse_tcp_url("127.0.0.1:9091"), ("127.0.0.1", 9091))


class ActorMessageTest(unittest.TestCase):
    def test_round_trip_bytes(self):
        msg = ActorMessage(topic="svc.ping", payload={"x": 1}, origin_node="a")
        cloned = ActorMessage.from_bytes(msg.to_bytes())
        self.assertEqual(cloned.id, msg.id)
        self.assertEqual(cloned.topic, "svc.ping")
        self.assertEqual(cloned.payload, {"x": 1})


class SocketActorMeshTest(unittest.TestCase):
    def test_two_node_fanout(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        bus_a = ServiceBus()
        bus_b = ServiceBus()
        mesh_a = ActorMesh(
            node_id="a",
            bus=bus_a,
            backend=SocketActorBackend(listen=listen, peers=[]),
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=bus_b,
            backend=SocketActorBackend(listen=None, peers=[listen]),
        )
        mesh_a.attach()
        mesh_b.attach()
        time.sleep(0.1)

        seen = []
        bus_b.subscribe("actor.ping", lambda p: seen.append(p))
        mesh_a.publish("actor.ping", {"ok": True})

        deadline = time.time() + 3
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(seen, [{"ok": True}])
        self.assertGreaterEqual(mesh_b.stats()["ingested"], 1)

        mesh_a.detach()
        mesh_b.detach()

    def test_build_disabled_by_default(self):
        self.assertIsNone(build_actor_mesh(ServiceBus(), cfg={"enabled": False}))


@unittest.skipUnless(nng_available(), "pynng not installed")
class NngActorMeshTest(unittest.TestCase):
    def test_bus0_fanout(self):
        port_a = _free_tcp_port()
        port_b = _free_tcp_port()
        url_a = format_tcp_url("127.0.0.1", port_a)
        url_b = format_tcp_url("127.0.0.1", port_b)

        bus_a = ServiceBus()
        bus_b = ServiceBus()
        mesh_a = ActorMesh(
            node_id="nng-a",
            bus=bus_a,
            backend=NngActorBackend(listen=url_a, peers=[url_b]),
        )
        mesh_b = ActorMesh(
            node_id="nng-b",
            bus=bus_b,
            backend=NngActorBackend(listen=url_b, peers=[url_a]),
        )
        mesh_a.attach()
        mesh_b.attach()
        time.sleep(0.15)

        seen = []
        bus_b.subscribe("nng.ping", lambda p: seen.append(p))

        # Bus0 can need a couple of tries while dials settle.
        for _ in range(5):
            mesh_a.publish("nng.ping", {"v": 1})
            deadline = time.time() + 1.0
            while not seen and time.time() < deadline:
                time.sleep(0.05)
            if seen:
                break
            time.sleep(0.1)

        self.assertEqual(seen[:1], [{"v": 1}])
        mesh_a.detach()
        mesh_b.detach()


class BootActorMeshTest(unittest.TestCase):
    def tearDown(self):
        shutdown()

    def test_boot_without_actor_mesh_by_default(self):
        shutdown()
        boot()
        from kernel.boot import get_kernel
        from kernel.contract import SERVICE_ACTOR_MESH, SERVICE_SERVICE_BUS

        k = get_kernel()
        self.assertTrue(k.container.has(SERVICE_SERVICE_BUS))
        self.assertFalse(k.container.has(SERVICE_ACTOR_MESH))
        shutdown()


if __name__ == "__main__":
    unittest.main()
