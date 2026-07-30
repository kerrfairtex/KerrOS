"""ADR-023: mTLS / NATS / remote process supervision foundation tests."""

from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from runtime.actor_mesh import ActorMesh, SocketActorBackend, build_actor_mesh, format_tcp_url
from runtime.actor_mesh_tls import (
    MeshTlsConfig,
    MeshTlsError,
    build_client_ssl_context,
    build_server_ssl_context,
)
from runtime.actor_remote_supervision import (
    RemoteRestartHook,
    RemoteSupervisionConfig,
    build_remote_restart_hook,
)
from runtime.actor_supervision import ActorHealth, ActorSupervisor, SupervisionConfig
from runtime.nats_actor_backend import (
    InMemoryNatsBroker,
    InMemoryNatsClient,
    NatsActorBackend,
    nats_available,
)
from runtime.service_bus import ServiceBus


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _write_self_signed(tmpdir: Path) -> tuple[str, str, str]:
    """Create a short-lived self-signed cert/key/CA via openssl (no extra deps)."""
    import subprocess

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
                "/CN=kerros-test",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise unittest.SkipTest(f"openssl cert generation unavailable: {exc}") from exc
    ca_path.write_bytes(cert_path.read_bytes())
    return str(ca_path), str(cert_path), str(key_path)


class MeshTlsConfigTest(unittest.TestCase):
    def test_defaults_disabled(self):
        cfg = MeshTlsConfig.from_mapping({})
        self.assertFalse(cfg.enabled)

    def test_validate_requires_paths(self):
        cfg = MeshTlsConfig(enabled=True, cert_file="", key_file="")
        with self.assertRaises(MeshTlsError):
            cfg.validate()


class MeshTlsLoopbackTest(unittest.TestCase):
    def test_tls_req_reply_loopback(self):
        with tempfile.TemporaryDirectory() as td:
            ca, cert, key = _write_self_signed(Path(td))
            tls = MeshTlsConfig(
                enabled=True,
                ca_file=ca,
                cert_file=cert,
                key_file=key,
                require_client_cert=True,
                check_hostname=False,
            )
            server_ctx = build_server_ssl_context(tls)
            client_ctx = build_client_ssl_context(tls)
            # mTLS lab mode: trust our CA, skip hostname (IP peer).
            import ssl as _ssl

            client_ctx.verify_mode = _ssl.CERT_REQUIRED
            client_ctx.check_hostname = False

            port = _free_tcp_port()
            listen = format_tcp_url("127.0.0.1", port)
            server_bus, client_bus = ServiceBus(), ServiceBus()
            server = ActorMesh(
                node_id="srv",
                bus=server_bus,
                backend=SocketActorBackend(
                    listen=listen,
                    peers=[],
                    ssl_server_context=server_ctx,
                    ssl_client_context=client_ctx,
                ),
            )
            client = ActorMesh(
                node_id="cli",
                bus=client_bus,
                backend=SocketActorBackend(
                    listen=None,
                    peers=[listen],
                    ssl_server_context=server_ctx,
                    ssl_client_context=client_ctx,
                ),
                routes={"echo": "srv"},
            )
            server.register("echo", lambda m: {"echo": m.payload.get("x")})
            server.attach()
            client.attach()
            try:
                out = client.request("echo", {"x": 7}, timeout_s=3.0)
                self.assertEqual(out.get("echo"), 7)
                self.assertTrue(server.backend.endpoints().get("tls"))
            finally:
                client.detach()
                server.detach()
                server.backend.close()
                client.backend.close()


class NatsBackendTest(unittest.TestCase):
    def test_nats_available_soft(self):
        # Just ensure the helper does not raise.
        self.assertIsInstance(nats_available(), bool)

    def test_inmemory_nats_fanout(self):
        broker = InMemoryNatsBroker()
        a = NatsActorBackend(
            node_id="a",
            subject_prefix="kerros.test",
            client=InMemoryNatsClient(broker),
        )
        b = NatsActorBackend(
            node_id="b",
            subject_prefix="kerros.test",
            client=InMemoryNatsClient(broker),
        )
        a.start()
        b.start()
        try:
            bus_a, bus_b = ServiceBus(), ServiceBus()
            mesh_a = ActorMesh(node_id="a", bus=bus_a, backend=a)
            mesh_b = ActorMesh(node_id="b", bus=bus_b, backend=b, routes={"echo": "a"})
            mesh_a.register("echo", lambda m: {"ok": m.payload.get("n")})
            mesh_a.attach()
            mesh_b.attach()
            try:
                out = mesh_b.request("echo", {"n": 3}, timeout_s=3.0)
                self.assertEqual(out.get("ok"), 3)
            finally:
                mesh_a.detach()
                mesh_b.detach()
        finally:
            a.close()
            b.close()

    def test_build_falls_back_without_nats(self):
        mesh = build_actor_mesh(
            ServiceBus(),
            cfg={
                "enabled": True,
                "backend": "nats",
                "listen": None,
                "peers": [],
            },
        )
        self.assertIsNotNone(mesh)
        assert mesh is not None
        # Soft fallback to socket when nats-py missing and no injected client.
        self.assertEqual(mesh.backend.endpoints().get("backend"), "socket")
        mesh.detach()
        mesh.backend.close()


class RemoteRestartTest(unittest.TestCase):
    def test_hook_calls_manager(self):
        manager = MagicMock()
        manager.restart.return_value = True
        hook = RemoteRestartHook(
            process_map={"worker": "code-agent"}, manager=manager
        )
        from runtime.actor_supervision import ActorLiveness

        row = ActorLiveness(name="worker", status=ActorHealth.DEAD)
        hook("worker", row)
        manager.restart.assert_called_once_with("code-agent")
        self.assertTrue(hook.attempts[0]["restarted"])

    def test_supervisor_wires_remote_restart(self):
        manager = MagicMock()
        manager.restart.return_value = True
        mesh = ActorMesh(
            node_id="solo",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[]),
        )
        cfg = RemoteSupervisionConfig(
            remote_restart=True, process_map={"echo": "echo-svc"}
        )
        hook = build_remote_restart_hook(cfg=cfg, manager=manager)
        self.assertIsNotNone(hook)
        sup = ActorSupervisor(
            mesh=mesh,
            config=SupervisionConfig(enabled=True, ttl_s=0.2, suspect_after_s=0.1),
            on_dead=hook,
        )
        from unittest.mock import patch

        t0 = 5000.0
        with patch("runtime.actor_supervision.time.time", return_value=t0):
            sup.observe("echo")
        with patch("runtime.actor_supervision.time.time", return_value=t0 + 1.0):
            dead = sup.sweep(now=t0 + 1.0)
        self.assertEqual(len(dead), 1)
        manager.restart.assert_called_once_with("echo-svc")

    def test_build_actor_mesh_remote_hook(self):
        manager = MagicMock()
        manager.restart.return_value = True
        mesh = build_actor_mesh(
            ServiceBus(),
            cfg={
                "enabled": True,
                "backend": "socket",
                "supervision": {
                    "enabled": True,
                    "remote_restart": True,
                    "process_map": {"echo": "svc"},
                    "ttl_s": 0.2,
                    "suspect_after_s": 0.1,
                },
                "_service_manager": manager,
            },
        )
        self.assertIsNotNone(mesh)
        assert mesh is not None and mesh.supervisor is not None
        self.assertIsNotNone(mesh.supervisor.on_dead)
        mesh.detach()
        mesh.backend.close()

    def test_remote_config_env_map(self):
        import os
        from unittest.mock import patch

        with patch.dict(
            os.environ,
            {
                "KERROS_ACTOR_MESH_REMOTE_RESTART": "1",
                "KERROS_ACTOR_MESH_PROCESS_MAP": "a=svc-a,b=svc-b",
            },
        ):
            cfg = RemoteSupervisionConfig.from_mapping({})
        self.assertTrue(cfg.remote_restart)
        self.assertEqual(cfg.process_map["a"], "svc-a")
        self.assertEqual(cfg.process_map["b"], "svc-b")


if __name__ == "__main__":
    unittest.main()
