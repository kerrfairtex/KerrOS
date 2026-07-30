"""ADR-039: in-cluster operator + CMDB sync + systemd timer tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.cmdb_client import (
    CmdbClientConfig,
    CmdbSyncClient,
    FakeCmdbSource,
    build_cmdb_sync_client,
)
from runtime.fleet_inventory import FleetInventory, FleetInventoryConfig
from runtime.k8s_incluster_operator import (
    FakeInformer,
    InClusterNatsOperator,
    InClusterOperatorConfig,
    build_incluster_nats_operator,
    detect_in_cluster,
)
from runtime.k8s_operator import FakeK8sCluster
from runtime.systemd_timers import (
    SystemdTimerConfig,
    SystemdTimerPackager,
    build_systemd_timer_packager,
)


class InClusterOperatorTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(InClusterOperatorConfig.from_mapping({}).enabled)
        self.assertIsNone(build_incluster_nats_operator({}))

    def test_reconcile_once_fake(self):
        informer = FakeInformer()
        informer.set_desired(["nats-a", "nats-b"])
        cluster = FakeK8sCluster()
        op = InClusterNatsOperator(
            cfg=InClusterOperatorConfig(enabled=True, require_in_cluster=False),
            informer=informer,
            cluster=cluster,
        )
        out = op.reconcile_once()
        self.assertTrue(out["ok"])
        self.assertEqual(len(cluster.list_resources()), 2)
        informer.set_desired(["nats-a"])
        out2 = op.reconcile_once()
        self.assertTrue(out2["ok"])
        self.assertEqual(len(cluster.list_resources()), 1)
        det = detect_in_cluster()
        self.assertIn("in_cluster", det)


class CmdbSyncTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(CmdbClientConfig.from_mapping({}).enabled)
        self.assertIsNone(build_cmdb_sync_client({}))

    def test_sync_into_inventory(self):
        inv = FleetInventory(cfg=FleetInventoryConfig(enabled=True))
        src = FakeCmdbSource(
            hosts=[
                {
                    "name": "east",
                    "address": "east.example",
                    "region": "us-east",
                    "members": ["nats-a"],
                }
            ]
        )
        client = CmdbSyncClient(
            cfg=CmdbClientConfig(enabled=True, backend="fake"),
            source=src,
            inventory=inv,
        )
        out = client.sync()
        self.assertTrue(out["ok"])
        self.assertEqual(out["upserted"], 1)
        self.assertEqual(inv.get("east").address, "east.example")


class SystemdTimerTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SystemdTimerConfig.from_mapping({}).enabled)
        self.assertIsNone(build_systemd_timer_packager({}))

    def test_render_and_write(self):
        with tempfile.TemporaryDirectory() as td:
            packager = SystemdTimerPackager(
                cfg=SystemdTimerConfig(
                    enabled=True,
                    units_dir=td,
                    allow_write=True,
                    org_name="Lab",
                    on_calendar="weekly",
                )
            )
            service = packager.render_service()
            timer = packager.render_timer()
            self.assertIn("[Service]", service)
            self.assertIn("OnCalendar=weekly", timer)
            out = packager.write_units()
            self.assertTrue(out["ok"])
            self.assertTrue(Path(out["service_path"]).is_file())
            self.assertTrue(Path(out["timer_path"]).is_file())
            # install to temp root
            install_root = Path(td) / "etc"
            packager.cfg.allow_install = True
            packager.cfg.install_root = str(install_root)
            installed = packager.install_units()
            self.assertTrue(installed["ok"])
            self.assertTrue((install_root / "kerros-acme-renew.timer").is_file())


if __name__ == "__main__":
    unittest.main()
