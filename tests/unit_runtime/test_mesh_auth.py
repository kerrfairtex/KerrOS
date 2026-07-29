"""Authenticated mesh tests (ADR-014)."""

from __future__ import annotations

import json
import time
import unittest
import urllib.error
import urllib.request

from runtime.actor_mesh import ActorMesh, SocketActorBackend, format_tcp_url
from runtime.event_bus import EventBus
from runtime.event_mesh import HttpEventMeshTransport, LocalEventMesh
from runtime.event_mesh_http import start_mesh_http_server
from runtime.mesh_auth import (
    MeshAuth,
    check_http_auth,
    extract_http_token,
    mesh_auth_from_config,
    tokens_equal,
    unwrap_actor_payload,
    wrap_actor_payload,
)
from runtime.service_bus import ServiceBus
import socket


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class MeshAuthUnitTest(unittest.TestCase):
    def test_tokens_equal(self):
        self.assertTrue(tokens_equal("", None))
        self.assertTrue(tokens_equal("abc", "abc"))
        self.assertFalse(tokens_equal("abc", "xyz"))

    def test_extract_bearer(self):
        self.assertEqual(
            extract_http_token({"Authorization": "Bearer secret"}),
            "secret",
        )
        self.assertEqual(
            extract_http_token({"X-Kerros-Mesh-Token": "t2"}),
            "t2",
        )

    def test_check_http_auth(self):
        auth = MeshAuth(token="s3cr3t")
        self.assertTrue(
            check_http_auth({"Authorization": "Bearer s3cr3t"}, auth)
        )
        self.assertFalse(check_http_auth({}, auth))
        self.assertTrue(check_http_auth({}, MeshAuth()))

    def test_actor_envelope(self):
        auth = MeshAuth(token="tok")
        wrapped = wrap_actor_payload({"topic": "a", "payload": {}}, auth)
        self.assertEqual(wrapped["token"], "tok")
        inner = unwrap_actor_payload(wrapped, auth)
        self.assertEqual(inner["topic"], "a")
        with self.assertRaises(PermissionError):
            unwrap_actor_payload({"token": "bad", "msg": {"topic": "a"}}, auth)

    def test_auth_required_without_token(self):
        auth = MeshAuth(token="", required=True)
        with self.assertRaises(RuntimeError):
            auth.ensure_ready()


class AuthenticatedHttpMeshTest(unittest.TestCase):
    def test_rejects_without_token_and_accepts_with(self):
        auth = MeshAuth(token="lab-token")
        bus_b = EventBus()
        mesh_b = LocalEventMesh(
            node_id="b",
            buses=[bus_b],
            transport=HttpEventMeshTransport(peers=[], auth=auth),
        )
        mesh_b.attach()
        server_b = start_mesh_http_server(
            mesh_b, listen="127.0.0.1:0", auth=auth
        )
        mesh_b.http_server = server_b

        bus_a = EventBus()
        mesh_a = LocalEventMesh(
            node_id="a",
            buses=[bus_a],
            transport=HttpEventMeshTransport(
                peers=[server_b.url_ingest], auth=auth
            ),
        )
        mesh_a.attach()

        # Unauthenticated ingest → 401
        body = json.dumps(
            {
                "origin_node": "a",
                "event": {
                    "id": "e1",
                    "topic": "auth.ping",
                    "payload": {"n": 1},
                    "timestamp": time.time(),
                    "source": "a",
                },
            }
        ).encode()
        bad = urllib.request.Request(
            server_b.url_ingest,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(bad, timeout=3)
        self.assertEqual(ctx.exception.code, 401)

        seen = []
        bus_b.subscribe("auth.ping", lambda e: seen.append(e.payload))
        mesh_a.publish_local("auth.ping", {"n": 1})
        deadline = time.time() + 3
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(seen, [{"n": 1}])

        mesh_a.detach()
        mesh_b.detach()


class AuthenticatedActorMeshTest(unittest.TestCase):
    def test_matching_tokens_fanout(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        auth = MeshAuth(token="actor-secret")
        bus_a, bus_b = ServiceBus(), ServiceBus()
        mesh_a = ActorMesh(
            node_id="a",
            bus=bus_a,
            backend=SocketActorBackend(listen=listen, peers=[]),
            auth=auth,
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=bus_b,
            backend=SocketActorBackend(listen=None, peers=[listen]),
            auth=auth,
        )
        mesh_a.attach()
        mesh_b.attach()
        time.sleep(0.1)
        seen = []
        bus_b.subscribe("auth.actor", lambda p: seen.append(p))
        mesh_a.publish("auth.actor", {"ok": True})
        deadline = time.time() + 3
        while not seen and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(seen, [{"ok": True}])
        mesh_a.detach()
        mesh_b.detach()

    def test_mismatched_token_rejected(self):
        port = _free_tcp_port()
        listen = format_tcp_url("127.0.0.1", port)
        mesh_a = ActorMesh(
            node_id="a",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=listen, peers=[]),
            auth=MeshAuth(token="good"),
        )
        mesh_b = ActorMesh(
            node_id="b",
            bus=ServiceBus(),
            backend=SocketActorBackend(listen=None, peers=[listen]),
            auth=MeshAuth(token="bad"),
        )
        mesh_a.attach()
        mesh_b.attach()
        time.sleep(0.1)
        seen = []
        mesh_b.bus.subscribe("auth.actor", lambda p: seen.append(p))
        mesh_a.publish("auth.actor", {"ok": True})
        time.sleep(0.4)
        self.assertEqual(seen, [])
        self.assertGreaterEqual(mesh_b.stats()["auth_rejected"], 1)
        mesh_a.detach()
        mesh_b.detach()


class MeshAuthFromConfigTest(unittest.TestCase):
    def test_env_token(self):
        import os

        prev = os.environ.get("KERROS_EVENT_MESH_TOKEN")
        try:
            os.environ["KERROS_EVENT_MESH_TOKEN"] = "from-env"
            auth = mesh_auth_from_config({"auth_token": "from-cfg"})
            self.assertEqual(auth.token, "from-env")
        finally:
            if prev is None:
                os.environ.pop("KERROS_EVENT_MESH_TOKEN", None)
            else:
                os.environ["KERROS_EVENT_MESH_TOKEN"] = prev


if __name__ == "__main__":
    unittest.main()
