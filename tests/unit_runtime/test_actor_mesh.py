"""IPC actor-mesh tests (C-16 / ADR-012 + ADR-018 orchestrator)."""

from __future__ import annotations

import os
import socket
import time
import unittest
from unittest.mock import patch

from runtime.actor_mesh import (
    ActorMesh,
    ActorMessage,
    NngActorBackend,
    SocketActorBackend,
    build_actor_mesh,
    format_tcp_url,
    listen_is_loopback,
    nng_available,
    parse_routes,
    parse_tcp_url,
)
from runtime.mesh_auth import MeshAuth
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


class ActorOrchestratorTest(unittest.TestCase):
    def test_parse_routes_and_loopback(self):
        self.assertEqual(parse_routes("echo=node-b,ping=a"), {"echo": "node-b", "ping": "a"})
        self.assertEqual(parse_routes({"echo": "b"}), {"echo": "b"})
        self.assertTrue(listen_is_loopback("tcp://127.0.0.1:9091"))
        self.assertFalse(listen_is_loopback("tcp://0.0.0.0:9091"))

    def test_request_reply_two_nodes(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            routes={"echo": "b"},
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
        )
        mesh_b.register("echo", lambda msg: {"echo": msg.payload.get("x"), "ok": True})
        mesh_b.attach()
        mesh_a.attach()
        time.sleep(0.1)

        out = mesh_a.request("echo", {"x": 42}, timeout_s=3.0)
        self.assertEqual(out, {"echo": 42, "ok": True})
        self.assertGreaterEqual(mesh_a.stats()["requests"], 1)

        mesh_a.detach()
        mesh_b.detach()

    def test_request_timeout(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        # Peer is connected but route targets a node that never receives
        # (target_node filter drops the req on both peers).
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            routes={"ghost": "ghost-node"},
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
        )
        mesh_b.attach()
        mesh_a.attach()
        time.sleep(0.05)
        with self.assertRaises(TimeoutError):
            mesh_a.request("ghost", {"x": 1}, timeout_s=0.3)
        mesh_a.detach()
        mesh_b.detach()

    def test_target_node_skips_other_peers(self):
        port_b = _free_tcp_port()
        port_c = _free_tcp_port()
        listen_b = format_tcp_url("127.0.0.1", port_b)
        listen_c = format_tcp_url("127.0.0.1", port_c)

        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen_b, listen_c]),
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen_b, peers=[]),
        )
        mesh_c = ActorMesh(
            node_id="c",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen_c, peers=[]),
        )
        seen_b, seen_c = [], []
        mesh_b.bus.subscribe("targeted", lambda p: seen_b.append(p))
        mesh_c.bus.subscribe("targeted", lambda p: seen_c.append(p))
        mesh_b.attach()
        mesh_c.attach()
        mesh_a.attach()
        time.sleep(0.15)

        mesh_a.publish("targeted", {"to": "b"}, target_node="b")
        deadline = time.time() + 2
        while not seen_b and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual(seen_b, [{"to": "b"}])
        self.assertEqual(seen_c, [])

        mesh_a.detach()
        mesh_b.detach()
        mesh_c.detach()

    def test_add_peer_after_attach(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
            routes={"echo": "a"},
        )
        mesh_a.register("echo", lambda msg: {"pong": True})
        mesh_a.attach()
        mesh_b.attach()
        mesh_b.add_peer(listen)
        time.sleep(0.1)

        out = mesh_b.request("echo", {}, timeout_s=3.0)
        self.assertEqual(out, {"pong": True})
        mesh_a.detach()
        mesh_b.detach()

    def test_routes_from_build_actor_mesh(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        with patch.dict(os.environ, {"KERROS_ACTOR_MESH": "1"}, clear=False):
            mesh = build_actor_mesh(
                ServiceBus(),
                cfg={
                    "enabled": True,
                    "node_id": "builder",
                    "listen": listen,
                    "peers": [],
                    "routes": {"echo": "remote"},
                },
            )
        self.assertIsNotNone(mesh)
        assert mesh is not None
        self.assertEqual(mesh.routes.get("echo"), "remote")
        mesh.detach()

    def test_local_request_without_route(self):
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        mesh.register("local", lambda msg: {"n": msg.payload.get("n", 0) + 1})
        mesh.attach()
        self.assertEqual(mesh.request("local", {"n": 2}), {"n": 3})
        mesh.detach()

    def test_non_loopback_requires_token(self):
        with self.assertRaises(RuntimeError):
            build_actor_mesh(
                ServiceBus(),
                cfg={
                    "enabled": True,
                    "listen": "tcp://0.0.0.0:19091",
                    "auth_required_non_loopback": True,
                    "auth_token": "",
                },
            )

    def test_request_reply_with_auth(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        auth = MeshAuth(token="orch-secret")
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            auth=auth,
            routes={"echo": "b"},
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
            auth=auth,
        )
        mesh_b.register("echo", lambda msg: {"auth": True})
        mesh_b.attach()
        mesh_a.attach()
        time.sleep(0.1)
        self.assertEqual(mesh_a.request("echo", {}, timeout_s=3.0), {"auth": True})
        mesh_a.detach()
        mesh_b.detach()


if __name__ == "__main__":
    unittest.main()

