"""ADR-020: actor mesh supervision foundation tests."""

from __future__ import annotations

import os
import socket
import time
import unittest
from unittest.mock import patch

from runtime.actor_mesh import ActorMesh, SocketActorBackend, build_actor_mesh, format_tcp_url
from runtime.actor_supervision import ActorHealth, ActorSupervisor, SupervisionConfig
from runtime.service_bus import ServiceBus


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class ActorSupervisionUnitTest(unittest.TestCase):
    def test_observe_beat_alive(self):
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        sup = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, ttl_s=30, suspect_after_s=10),
        )
        mesh.supervisor = sup
        mesh.register("echo", lambda m: {"ok": True})
        row = sup.table()["echo"]
        self.assertEqual(row.status, ActorHealth.ALIVE)
        before = row.last_beat
        time.sleep(0.02)
        sup.beat("echo", meta={"n": 1})
        row2 = sup.table()["echo"]
        self.assertGreaterEqual(row2.last_beat, before)
        self.assertEqual(row2.meta.get("n"), 1)

    def test_sweep_suspect_then_dead(self):
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        sup = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(
                enabled=True, ttl_s=1.0, suspect_after_s=0.4, heartbeat_interval_s=0
            ),
        )
        t0 = 1000.0
        with patch("runtime.actor_supervision.time.time", return_value=t0):
            sup.observe("echo")
        with patch("runtime.actor_supervision.time.time", return_value=t0 + 0.5):
            sup.sweep(now=t0 + 0.5)
        self.assertEqual(sup.table()["echo"].status, ActorHealth.SUSPECT)
        with patch("runtime.actor_supervision.time.time", return_value=t0 + 1.5):
            dead = sup.sweep(now=t0 + 1.5)
        self.assertEqual(sup.table()["echo"].status, ActorHealth.DEAD)
        self.assertEqual(len(dead), 1)

    def test_on_dead_hook_once(self):
        fired: list[str] = []
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        sup = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, ttl_s=0.2, suspect_after_s=0.1),
            on_dead=lambda name, row: fired.append(name),
        )
        t0 = 2000.0
        with patch("runtime.actor_supervision.time.time", return_value=t0):
            sup.observe("x")
        with patch("runtime.actor_supervision.time.time", return_value=t0 + 1.0):
            sup.sweep(now=t0 + 1.0)
            sup.sweep(now=t0 + 2.0)
        self.assertEqual(fired, ["x"])

    def test_unregister_forgets(self):
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        mesh.supervisor = ActorSupervisor(mesh=mesh, config=SupervisionConfig(enabled=True))
        mesh.register("echo", lambda m: {})
        self.assertIn("echo", mesh.supervisor.table())
        mesh.unregister("echo")
        self.assertNotIn("echo", mesh.supervisor.table())

    def test_sys_ping_local(self):
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        mesh.supervisor = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, auto_register_ping=True),
        )
        mesh.attach()
        out = mesh.request("_sys.ping", {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("node_id"), "solo")
        self.assertIn("_sys.ping", out.get("handlers") or [])
        mesh.detach()


class ActorSupervisionMeshTest(unittest.TestCase):
    def test_remote_ping_via_request(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
        )
        mesh_b.supervisor = ActorSupervisor(
            mesh=mesh_b,
            config=SupervisionConfig(enabled=True, auto_register_ping=True),
        )
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            routes={"_sys.ping": "b"},
        )
        mesh_a.supervisor = ActorSupervisor(
            mesh=mesh_a,
            config=SupervisionConfig(enabled=True, ping_timeout_s=3.0),
        )
        mesh_b.attach()
        mesh_a.attach()
        time.sleep(0.1)
        out = mesh_a.supervisor.ping("_sys.ping", timeout_s=3.0)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("node_id"), "b")
        mesh_a.detach()
        mesh_b.detach()

    def test_ping_timeout(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            routes={"_sys.ping": "ghost"},
        )
        mesh_a.supervisor = ActorSupervisor(
            mesh=mesh_a,
            config=SupervisionConfig(enabled=True, ping_timeout_s=0.3),
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
            mesh_a.supervisor.ping(timeout_s=0.3)
        mesh_a.detach()
        mesh_b.detach()

    def test_build_supervision_disabled_by_default(self):
        with patch.dict(os.environ, {"KERROS_ACTOR_MESH": "1"}, clear=False):
            port = _free_tcp_port()
            mesh = build_actor_mesh(
                ServiceBus(),
                cfg={
                    "enabled": True,
                    "listen": format_tcp_url("127.0.0.1", port),
                    "peers": [],
                },
            )
        self.assertIsNotNone(mesh)
        assert mesh is not None
        self.assertIsNone(mesh.supervisor)
        self.assertIsNone(mesh.stats().get("supervision"))
        mesh.detach()

    def test_build_enables_supervision(self):
        with patch.dict(os.environ, {"KERROS_ACTOR_MESH": "1"}, clear=False):
            port = _free_tcp_port()
            mesh = build_actor_mesh(
                ServiceBus(),
                cfg={
                    "enabled": True,
                    "listen": format_tcp_url("127.0.0.1", port),
                    "peers": [],
                    "supervision": {"enabled": True, "auto_register_ping": True},
                },
            )
        self.assertIsNotNone(mesh)
        assert mesh is not None
        self.assertIsNotNone(mesh.supervisor)
        self.assertIn("_sys.ping", mesh.stats()["handlers"])
        self.assertIsNotNone(mesh.stats()["supervision"])
        mesh.detach()


if __name__ == "__main__":
    unittest.main()
