"""ADR-030: Supercluster topology + ACME HTTP-01 solver tests."""

from __future__ import annotations

import urllib.error
import urllib.request
import unittest

from runtime.acme_http01 import AcmeHttp01Config, AcmeHttp01Solver, build_acme_http01_solver
from runtime.nats_supercluster import (
    SuperclusterConfig,
    SuperclusterTopology,
    SuperclusterTopologyError,
    build_supercluster_topology,
)


class SuperclusterTopologyTest(unittest.TestCase):
    def test_config_default_off(self):
        cfg = SuperclusterConfig.from_mapping({})
        self.assertFalse(cfg.enabled)
        self.assertIsNone(build_supercluster_topology({}))

    def test_valid_clusters_and_gateway(self):
        topo = SuperclusterTopology.from_config(
            SuperclusterConfig(
                enabled=True,
                name="lab",
                clusters=[
                    {"name": "east", "urls": ["nats://east:4222"], "region": "us-east"},
                    {"name": "west", "urls": ["nats://west:4222"], "region": "us-west"},
                ],
                gateways=[{"from": "east", "to": "west", "gateway_url": "nats://gw:7222"}],
                leafnodes=[{"name": "edge-1", "urls": ["nats://edge:7422"]}],
            )
        )
        self.assertEqual(topo.validate(), [])
        self.assertTrue(topo.is_valid())
        stats = topo.stats()
        self.assertEqual(stats["nodes"], 3)
        self.assertEqual(stats["gateways"], 1)
        self.assertEqual(stats["by_role"]["cluster"], 2)
        self.assertEqual(stats["by_role"]["leaf"], 1)
        self.assertEqual(topo.cluster_urls("east"), ["nats://east:4222"])

    def test_gateway_unknown_cluster(self):
        topo = SuperclusterTopology.from_config(
            SuperclusterConfig(
                enabled=True,
                clusters=[{"name": "east", "urls": ["nats://east:4222"]}],
                gateways=[{"from": "east", "to": "missing"}],
            )
        )
        errors = topo.validate()
        self.assertTrue(any("unknown" in e for e in errors))
        self.assertFalse(topo.is_valid())

    def test_gateway_from_leaf_rejected(self):
        topo = SuperclusterTopology.from_config(
            SuperclusterConfig(
                enabled=True,
                clusters=[{"name": "hub", "urls": ["nats://hub:4222"]}],
                leafnodes=[{"name": "edge", "urls": ["nats://edge:7422"]}],
                gateways=[{"from": "edge", "to": "hub"}],
            )
        )
        errors = topo.validate()
        self.assertTrue(any("role=cluster" in e for e in errors))

    def test_duplicate_node_raises(self):
        with self.assertRaises(SuperclusterTopologyError):
            SuperclusterTopology.from_config(
                SuperclusterConfig(
                    enabled=True,
                    clusters=[
                        {"name": "a", "urls": ["nats://a:4222"]},
                        {"name": "a", "urls": ["nats://b:4222"]},
                    ],
                )
            )


class AcmeHttp01Test(unittest.TestCase):
    def test_config_default_off(self):
        cfg = AcmeHttp01Config.from_mapping({})
        self.assertFalse(cfg.enabled)
        self.assertIsNone(build_acme_http01_solver({}))

    def test_serve_challenge_and_miss(self):
        solver = AcmeHttp01Solver(
            cfg=AcmeHttp01Config(enabled=True, bind="127.0.0.1", port=0)
        )
        solver.start()
        self.addCleanup(solver.stop)
        self.assertTrue(solver.stats()["listening"])
        self.assertGreater(solver.cfg.port, 0)

        solver.put_challenge("tok-abc", "key-auth-xyz")
        url = solver.challenge_url("tok-abc")
        with urllib.request.urlopen(url, timeout=2) as resp:
            body = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertEqual(body, "key-auth-xyz")

        miss = solver.challenge_url("nope")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(miss, timeout=2)
        self.assertEqual(ctx.exception.code, 404)

        solver.clear_challenge("tok-abc")
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(url, timeout=2)
        self.assertEqual(ctx2.exception.code, 404)

        stats = solver.stats()
        self.assertGreaterEqual(stats["hits"], 1)
        self.assertGreaterEqual(stats["misses"], 2)


if __name__ == "__main__":
    unittest.main()
