"""ADR-028: JetStream soft client, OTP supervision tree, CA reload tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.actor_mesh import ActorMesh, SocketActorBackend, build_actor_mesh
from runtime.actor_mesh_tls import (
    MeshTlsConfig,
    ReloadingTlsHolder,
    contexts_stale,
    pem_mtimes,
    reload_ssl_contexts,
)
from runtime.actor_supervision import ActorHealth, ActorSupervisor, SupervisionConfig
from runtime.actor_supervision_tree import SupervisionTree, build_supervision_tree
from runtime.nats_jetstream import (
    InMemoryJetStreamBroker,
    InMemoryJetStreamClient,
    JetStreamSoftClient,
    jetstream_config_from,
)
from runtime.service_bus import ServiceBus


def _write_self_signed(tmpdir: Path) -> tuple[str, str, str]:
    key_path = tmpdir / "key.pem"
    cert_path = tmpdir / "cert.pem"
    ca_path = tmpdir / "ca.pem"
    try:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=kerros-reload-test",
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise unittest.SkipTest(f"openssl unavailable: {exc}") from exc
    ca_path.write_bytes(cert_path.read_bytes())
    return str(ca_path), str(cert_path), str(key_path)


class JetStreamSoftTest(unittest.TestCase):
    def test_config_default_off(self):
        cfg = jetstream_config_from({})
        self.assertFalse(cfg.enabled)

    def test_inmemory_durable_publish(self):
        broker = InMemoryJetStreamBroker()
        client = InMemoryJetStreamClient(broker, stream="kerros")
        soft = JetStreamSoftClient(
            cfg=jetstream_config_from(
                {"enabled": True, "stream": "kerros", "durable": "d1"}
            ),
            client=client,
        )
        soft.start()
        try:
            ack = soft.publish("kerros.actor.broadcast", b"hello")
            self.assertEqual(ack["seq"], 1)
            self.assertEqual(broker.stream_len("kerros"), 1)
            received: list[bytes] = []

            async def _sub() -> None:
                def _cb(msg):
                    received.append(msg.data)

                await client.subscribe("kerros.actor.broadcast", _cb, durable="d1")

            asyncio.run(_sub())
            self.assertEqual(received, [b"hello"])
        finally:
            soft.close()

    def test_build_mesh_with_injected_jetstream(self):
        broker = InMemoryJetStreamBroker()
        injected = InMemoryJetStreamClient(broker)
        mesh = build_actor_mesh(
            ServiceBus(),
            cfg={
                "enabled": True,
                "backend": "socket",
                "_jetstream_client": injected,
                "nats": {"jetstream": {"enabled": False}},
            },
        )
        self.assertIsNotNone(mesh)
        assert mesh is not None
        self.assertIsNotNone(mesh.jetstream)
        mesh.jetstream.publish("t", b"x")
        self.assertEqual(broker.stream_len("kerros"), 1)
        mesh.detach()
        mesh.backend.close()
        mesh.jetstream.close()


class SupervisionTreeTest(unittest.TestCase):
    def test_build_default_none(self):
        self.assertIsNone(build_supervision_tree(enabled=False))

    def test_one_for_one_forgets_children(self):
        bus = ServiceBus()
        mesh = ActorMesh(
            node_id="solo",
            bus=bus,
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        parent = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, ttl_s=0.2, suspect_after_s=0.1),
        )
        child = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, ttl_s=30.0, suspect_after_s=10.0),
        )
        child.observe("worker")
        self.assertIn("worker", child.table())

        tree = SupervisionTree(strategy="one_for_one")
        tree.add_child("boss", child)
        tree.wire_parent("boss", parent)
        parent.observe("boss")

        t0 = 9000.0
        with patch("runtime.actor_supervision.time.time", return_value=t0):
            parent.observe("boss")
        with patch("runtime.actor_supervision.time.time", return_value=t0 + 1.0):
            dead = parent.sweep(now=t0 + 1.0)
        self.assertEqual(len(dead), 1)
        self.assertNotIn("worker", child.table())
        self.assertTrue(tree.events())
        self.assertEqual(tree.events()[-1]["strategy"], "one_for_one")


class CaReloadTest(unittest.TestCase):
    def test_reload_on_mtime_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ca, cert, key = _write_self_signed(root)
            cfg = MeshTlsConfig(
                enabled=True,
                ca_file=ca,
                cert_file=cert,
                key_file=key,
                reload=True,
            )
            holder = ReloadingTlsHolder.from_config(cfg)
            self.assertEqual(holder.stats()["reloads"], 1)
            first = dict(holder.stats()["mtimes"])
            self.assertFalse(contexts_stale(cfg, first))

            # Bump cert mtime without corrupting PEM.
            time.sleep(0.05)
            Path(cert).touch()
            # Some filesystems have 1s mtime resolution — force newer stamp.
            os.utime(cert, (time.time() + 2, time.time() + 2))
            self.assertTrue(contexts_stale(cfg, first))
            self.assertTrue(holder.reload(force=False))
            self.assertEqual(holder.stats()["reloads"], 2)
            # No-op when unchanged.
            self.assertFalse(holder.reload(force=False))

    def test_reload_ssl_contexts_builds(self):
        with tempfile.TemporaryDirectory() as td:
            ca, cert, key = _write_self_signed(Path(td))
            cfg = MeshTlsConfig(
                enabled=True, ca_file=ca, cert_file=cert, key_file=key
            )
            server, client, mtimes = reload_ssl_contexts(cfg)
            self.assertIsNotNone(server)
            self.assertIsNotNone(client)
            self.assertEqual(mtimes, pem_mtimes(cfg))


if __name__ == "__main__":
    unittest.main()
