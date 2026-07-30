"""ADR-038: fleet inventory + K8s operator + ACME renewal timer tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.acme_production import AcmeProductionClient, AcmeProductionConfig, FakePackagedAcme
from runtime.acme_renewal_timer import (
    AcmeRenewalConfig,
    AcmeRenewalTimer,
    build_acme_renewal_timer,
)
from runtime.fleet_inventory import (
    FleetInventory,
    FleetInventoryConfig,
    InventoryHost,
    build_fleet_inventory,
)
from runtime.k8s_operator import (
    FakeK8sCluster,
    K8sFleetOperator,
    K8sOperatorConfig,
    build_k8s_fleet_operator,
    nats_broker_manifest,
)


class FleetInventoryTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(FleetInventoryConfig.from_mapping({}).enabled)
        self.assertIsNone(build_fleet_inventory({}))

    def test_upsert_export_persist(self):
        with tempfile.TemporaryDirectory() as td:
            inv = FleetInventory(
                cfg=FleetInventoryConfig(
                    enabled=True,
                    store_path=str(Path(td) / "inv.json"),
                    allow_persist=True,
                )
            )
            inv.upsert(
                InventoryHost(
                    name="east",
                    address="east.example",
                    region="us-east",
                    roles=["nats"],
                    members=["nats-a"],
                )
            )
            hosts = inv.export_remote_fleet_hosts()
            self.assertEqual(hosts[0]["host"], "east.example")
            self.assertEqual(hosts[0]["members"], ["nats-a"])
            out = inv.persist()
            self.assertTrue(out["ok"])
            inv2 = FleetInventory(
                cfg=FleetInventoryConfig(
                    enabled=True,
                    store_path=str(Path(td) / "inv.json"),
                )
            )
            loaded = inv2.load()
            self.assertTrue(loaded["ok"])
            self.assertEqual(inv2.get("east").address, "east.example")


class K8sOperatorTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(K8sOperatorConfig.from_mapping({}).enabled)
        self.assertIsNone(build_k8s_fleet_operator({}))

    def test_apply_reconcile_fake(self):
        op = K8sFleetOperator(
            cfg=K8sOperatorConfig(enabled=True, backend="fake"),
            backend=FakeK8sCluster(),
        )
        self.assertTrue(op.apply_broker("nats-east")["ok"])
        self.assertTrue(op.apply_broker("nats-west")["ok"])
        self.assertEqual(len(op.backend.list_resources()), 2)
        out = op.reconcile(["nats-east"])
        self.assertTrue(out["ok"])
        names = [r["metadata"]["name"] for r in op.backend.list_resources()]
        self.assertEqual(names, ["nats-east"])
        manifest = nats_broker_manifest("x", replicas=3)
        self.assertEqual(manifest["spec"]["replicas"], 3)


class AcmeRenewalTimerTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(AcmeRenewalConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_renewal_timer({}))

    def test_tick_uses_production(self):
        with tempfile.TemporaryDirectory() as td:
            prod = AcmeProductionClient(
                cfg=AcmeProductionConfig(
                    enabled=True,
                    domains=["example.com"],
                    live_dir=str(Path(td) / "live"),
                ),
                runner=FakePackagedAcme(),
            )
            timer = AcmeRenewalTimer(
                cfg=AcmeRenewalConfig(enabled=True, interval_s=3600),
                production=prod,
            )
            out = timer.tick()
            self.assertTrue(out["ok"])
            self.assertEqual(timer.stats()["ticks"], 1)
            # Custom renew_fn
            calls = []
            timer2 = AcmeRenewalTimer(
                cfg=AcmeRenewalConfig(enabled=True),
                renew_fn=lambda: calls.append(1) or {"ok": True, "custom": True},
            )
            self.assertTrue(timer2.tick()["custom"])
            self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
