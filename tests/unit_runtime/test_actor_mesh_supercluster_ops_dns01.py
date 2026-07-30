"""ADR-031: Supercluster ops + ACME account/DNS-01 tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.acme_account import (
    AcmeAccountConfig,
    AcmeAccountRegistry,
    build_acme_account_registry,
)
from runtime.acme_dns01 import (
    AcmeDns01Config,
    AcmeDns01Solver,
    build_acme_dns01_solver,
    dns01_name,
    dns01_txt_value,
)
from runtime.nats_supercluster import SuperclusterConfig, SuperclusterTopology
from runtime.nats_supercluster_ops import (
    SuperclusterOps,
    SuperclusterOpsConfig,
    build_supercluster_ops,
    parse_host_port,
)


def _lab_topology() -> SuperclusterTopology:
    return SuperclusterTopology.from_config(
        SuperclusterConfig(
            enabled=True,
            name="lab",
            clusters=[
                {"name": "east", "urls": ["nats://east:4222"]},
                {"name": "west", "urls": ["nats://west:4222"]},
            ],
            gateways=[{"from": "east", "to": "west", "gateway_url": "nats://gw:7222"}],
            leafnodes=[{"name": "edge", "urls": ["nats://edge:7422"]}],
        )
    )


class SuperclusterOpsTest(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(SuperclusterOpsConfig.from_mapping({}).enabled)
        self.assertIsNone(build_supercluster_ops({}))

    def test_plan_apply_and_snippets(self):
        topo = _lab_topology()
        ops = SuperclusterOps(
            cfg=SuperclusterOpsConfig(enabled=True, allow_probe=False),
            topology=topo,
        )
        plan = ops.plan()
        self.assertTrue(any(a["op"] == "gateway_link" for a in plan))
        self.assertTrue(any(a["op"] == "leafnode_attach" for a in plan))
        applied = ops.apply_plan()
        self.assertEqual(len(applied), len(plan))
        self.assertTrue(all(a["status"] == "applied" for a in applied))
        snippets = ops.render_nats_snippets()
        self.assertIn("gateway", snippets["gateways"])
        self.assertIn("leafnodes", snippets["leafnodes"])
        health = ops.health()
        self.assertTrue(health["topology_valid"])
        self.assertEqual(health["applied"], len(applied))

    def test_probe_disabled_by_default(self):
        ops = SuperclusterOps(
            cfg=SuperclusterOpsConfig(enabled=True, allow_probe=False),
            topology=_lab_topology(),
        )
        out = ops.probe_all()
        self.assertTrue(out[0].get("skipped"))

    def test_probe_with_fake_fn(self):
        def fake(url: str, timeout_s: float) -> dict:
            return {"url": url, "ok": url.endswith(":4222"), "timeout_s": timeout_s}

        ops = SuperclusterOps(
            cfg=SuperclusterOpsConfig(enabled=True, allow_probe=True),
            topology=_lab_topology(),
            probe_fn=fake,
        )
        results = ops.probe_all()
        self.assertEqual(len(results), 3)
        self.assertTrue(any(r["ok"] for r in results))
        self.assertEqual(parse_host_port("nats://east:4222"), ("east", 4222))


class AcmeAccountTest(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(AcmeAccountConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_account_registry({}))

    def test_dry_run_register_persists(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = AcmeAccountConfig(
                enabled=True,
                account_dir=td,
                contact_email="ops@example.com",
                dry_run=True,
            )
            reg = AcmeAccountRegistry(cfg=cfg)
            rec = reg.register()
            self.assertEqual(rec["status"], "registered")
            self.assertTrue(rec["dry_run"])
            self.assertTrue(str(rec["kid"]).startswith("local:"))
            path = Path(td) / "account.json"
            self.assertTrue(path.is_file())
            again = reg.register()
            self.assertEqual(again["kid"], rec["kid"])
            probe = reg.maybe_probe_directory()
            self.assertTrue(probe.get("skipped"))
            self.assertTrue(reg.stats()["registered"])


class AcmeDns01Test(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(AcmeDns01Config.from_mapping({}).enabled)
        self.assertIsNone(build_acme_dns01_solver({}))

    def test_txt_value_and_challenge_roundtrip(self):
        key_auth = "token.thumbprint"
        value = dns01_txt_value(key_auth)
        self.assertTrue(value)
        self.assertNotIn("=", value)
        self.assertEqual(dns01_name("example.com"), "_acme-challenge.example.com")

        solver = AcmeDns01Solver(cfg=AcmeDns01Config(enabled=True))
        put = solver.put_challenge("example.com", key_auth)
        self.assertEqual(put["value"], value)
        self.assertTrue(solver.verify_local("example.com", key_auth))
        self.assertEqual(solver.get_challenge("example.com"), value)
        solver.clear_challenge("example.com")
        self.assertIsNone(solver.get_challenge("example.com"))
        self.assertEqual(solver.stats()["puts"], 1)
        self.assertEqual(solver.stats()["clears"], 1)


if __name__ == "__main__":
    unittest.main()
