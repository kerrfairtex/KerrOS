"""ADR-040: CRD + commercial CMDB + distro package tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.cmdb_commercial import (
    CommercialCmdbClient,
    CommercialCmdbConfig,
    FakeServiceNowSource,
    build_commercial_cmdb,
)
from runtime.distro_packages import (
    DistroPackageConfig,
    DistroPackager,
    build_distro_packager,
    render_deb_control,
    render_rpm_spec,
)
from runtime.fleet_inventory import FleetInventory, FleetInventoryConfig
from runtime.k8s_crd import (
    K8sCrdConfig,
    K8sCrdFacade,
    build_k8s_crd,
    render_cr,
    render_nats_broker_crd,
    validate_crd,
)
from runtime.k8s_operator import FakeK8sCluster


class K8sCrdTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(K8sCrdConfig.from_mapping({}).enabled)
        self.assertIsNone(build_k8s_crd({}))

    def test_validate_and_apply_cr(self):
        doc = render_nats_broker_crd()
        self.assertEqual(validate_crd(doc), [])
        facade = K8sCrdFacade(
            cfg=K8sCrdConfig(enabled=True, backend="fake"),
            cluster=FakeK8sCluster(),
        )
        out = facade.apply_crd()
        self.assertTrue(out["ok"])
        cr_out = facade.apply_cr("nats-a", replicas=2)
        self.assertTrue(cr_out["ok"])
        cr = render_cr("nats-b")
        self.assertEqual(cr["kind"], "NatsBroker")
        with tempfile.TemporaryDirectory() as td:
            path = facade.write_crd_yaml(Path(td) / "natsbroker.yaml")
            self.assertTrue(path.is_file())
        self.assertGreaterEqual(facade.stats()["applies"], 2)


class CommercialCmdbTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(CommercialCmdbConfig.from_mapping({}).enabled)
        self.assertIsNone(build_commercial_cmdb({}))

    def test_sync_servicenow_fake(self):
        inv = FleetInventory(cfg=FleetInventoryConfig(enabled=True))
        client = CommercialCmdbClient(
            cfg=CommercialCmdbConfig(enabled=True, vendor="servicenow"),
            source=FakeServiceNowSource(),
            inventory=inv,
        )
        out = client.sync()
        self.assertTrue(out["ok"])
        self.assertEqual(out["upserted"], 2)
        self.assertEqual(inv.stats()["hosts"], 2)


class DistroPackageTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(DistroPackageConfig.from_mapping({}).enabled)
        self.assertIsNone(build_distro_packager({}))

    def test_preview_and_write_stubs(self):
        cfg = DistroPackageConfig(
            enabled=True,
            package_name="kerros",
            version="0.1.0",
            allow_write=False,
        )
        pkg = DistroPackager(cfg=cfg)
        preview = pkg.preview()
        self.assertIn("Package: kerros", preview["deb_control"])
        self.assertIn("Name:", preview["rpm_spec"])
        self.assertIn("kerros", render_deb_control(cfg))
        self.assertIn("kerros", render_rpm_spec(cfg))
        skipped = pkg.write_stubs()
        self.assertTrue(skipped.get("skipped"))
        with tempfile.TemporaryDirectory() as td:
            writable = DistroPackager(
                cfg=DistroPackageConfig(
                    enabled=True,
                    output_dir=td,
                    allow_write=True,
                    allow_install=True,
                )
            )
            out = writable.write_stubs()
            self.assertTrue(out["ok"])
            self.assertTrue(any(Path(p).is_file() for p in out["written"]))
            inst = writable.install_stub()
            self.assertTrue(inst["ok"])
            self.assertTrue(Path(inst["staged"]).is_dir())


if __name__ == "__main__":
    unittest.main()
