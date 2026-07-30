"""ADR-042: operator-sdk controller + vendor CMDB SDK + apt/yum publish tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.cmdb_vendor_sdk import (
    SoftPysnowSdk,
    VendorCmdbClient,
    VendorCmdbConfig,
    build_vendor_cmdb,
    pysnow_available,
)
from runtime.distro_publish import (
    DistroPublishConfig,
    DistroPublisher,
    FakeRepoPublisher,
    build_distro_publisher,
)
from runtime.fleet_inventory import FleetInventory, FleetInventoryConfig
from runtime.k8s_operator import FakeK8sCluster
from runtime.k8s_operator_sdk import (
    FakeLeaderElection,
    OperatorSdkConfig,
    OperatorSdkController,
    build_operator_sdk_controller,
)


class OperatorSdkTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(OperatorSdkConfig.from_mapping({}).enabled)
        self.assertIsNone(build_operator_sdk_controller({}))

    def test_reconcile_and_skeleton(self):
        ctl = OperatorSdkController(
            cfg=OperatorSdkConfig(enabled=True, backend="fake", allow_write=False),
            cluster=FakeK8sCluster(),
            leader=FakeLeaderElection(identity="ctl-0"),
        )
        crd = ctl.ensure_crd()
        self.assertTrue(crd["ok"])
        ctl.set_desired(["nats-a", "nats-b"])
        out = ctl.reconcile_once()
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["applied"]), 2)
        ctl.set_desired(["nats-a"])
        out2 = ctl.reconcile_once()
        self.assertEqual(out2["deleted"], ["nats-b"])
        skipped = ctl.write_project_skeleton()
        self.assertTrue(skipped.get("skipped"))
        with tempfile.TemporaryDirectory() as td:
            writable = OperatorSdkController(
                cfg=OperatorSdkConfig(
                    enabled=True, allow_write=True, project_dir=td
                ),
                cluster=FakeK8sCluster(),
            )
            written = writable.write_project_skeleton()
            self.assertTrue(written["ok"])
            self.assertTrue(any(Path(p).is_file() for p in written["written"]))
        dry = ctl.soft_operator_sdk_init()
        self.assertTrue(dry.get("dry_run"))


class VendorCmdbSdkTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(VendorCmdbConfig.from_mapping({}).enabled)
        self.assertIsNone(build_vendor_cmdb({}))

    def test_pysnow_soft_dry_run_sync(self):
        inv = FleetInventory(cfg=FleetInventoryConfig(enabled=True))
        client = VendorCmdbClient(
            cfg=VendorCmdbConfig(
                enabled=True, vendor="servicenow", backend="pysnow", allow_live=False
            ),
            sdk=SoftPysnowSdk(allow_live=False),
            inventory=inv,
        )
        out = client.sync()
        self.assertTrue(out["ok"])
        self.assertEqual(out["upserted"], 2)
        self.assertIsInstance(pysnow_available(), bool)
        self.assertEqual(inv.stats()["hosts"], 2)


class DistroPublishTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(DistroPublishConfig.from_mapping({}).enabled)
        self.assertIsNone(build_distro_publisher({}))

    def test_fake_publish(self):
        with tempfile.TemporaryDirectory() as td:
            pub = DistroPublisher(
                cfg=DistroPublishConfig(
                    enabled=True,
                    backend="fake",
                    staging_dir=td,
                    allow_write=True,
                    allow_publish=False,
                ),
                publisher=FakeRepoPublisher(),
            )
            staged = pub.stage_metadata()
            self.assertTrue(staged["ok"])
            out = pub.publish()
            self.assertTrue(out["ok"])
            self.assertEqual(out["backend"], "fake")
            self.assertTrue(Path(td).is_dir())


if __name__ == "__main__":
    unittest.main()
