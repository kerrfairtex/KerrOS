"""ADR-043: Go operator + vendor cert + remote mirror tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.cmdb_vendor_cert import (
    FakePartnershipProbe,
    VendorCertConfig,
    VendorCertRegistry,
    build_vendor_cert,
)
from runtime.distro_remote_mirror import (
    FakeRemoteMirror,
    RemoteMirrorConfig,
    RemoteMirrorPublisher,
    build_remote_mirror,
)
from runtime.k8s_go_operator import (
    GoOperatorConfig,
    GoOperatorPackager,
    build_go_operator,
)


class GoOperatorTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(GoOperatorConfig.from_mapping({}).enabled)
        self.assertIsNone(build_go_operator({}))

    def test_write_and_fake_build(self):
        with tempfile.TemporaryDirectory() as td:
            pkg = GoOperatorPackager(
                cfg=GoOperatorConfig(
                    enabled=True,
                    project_dir=td,
                    allow_write=True,
                    allow_build=False,
                )
            )
            written = pkg.write_sources()
            self.assertTrue(written["ok"])
            self.assertTrue((Path(td) / "main.go").is_file())
            built = pkg.build()
            self.assertTrue(built["ok"])
            self.assertTrue(built.get("dry_run"))
            self.assertTrue(Path(built["artifact"]).is_file())
            img = pkg.build_image()
            self.assertTrue(img.get("dry_run"))


class VendorCertTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(VendorCertConfig.from_mapping({}).enabled)
        self.assertIsNone(build_vendor_cert({}))

    def test_refresh_and_evidence(self):
        reg = VendorCertRegistry(
            cfg=VendorCertConfig(enabled=True, allow_write=False),
            probe=FakePartnershipProbe(),
        )
        programs = reg.list_programs()
        self.assertGreaterEqual(len(programs), 2)
        refreshed = reg.refresh()
        self.assertTrue(refreshed["ok"])
        evidence = reg.issue_evidence(programs[0]["id"])
        self.assertFalse(evidence["certified"])
        with tempfile.TemporaryDirectory() as td:
            writable = VendorCertRegistry(
                cfg=VendorCertConfig(
                    enabled=True, allow_write=True, output_dir=td
                ),
                probe=FakePartnershipProbe(),
            )
            out = writable.issue_evidence("servicenow-tech-partner")
            self.assertTrue(Path(out["path"]).is_file())


class RemoteMirrorTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(RemoteMirrorConfig.from_mapping({}).enabled)
        self.assertIsNone(build_remote_mirror({}))

    def test_fake_push(self):
        with tempfile.TemporaryDirectory() as td:
            pub = RemoteMirrorPublisher(
                cfg=RemoteMirrorConfig(
                    enabled=True,
                    staging_dir=td,
                    remote_url="rsync://mirror.test/kerros/",
                    allow_write=True,
                    allow_remote=False,
                ),
                backend=FakeRemoteMirror(),
            )
            staged = pub.stage_marker()
            self.assertTrue(staged["ok"])
            out = pub.push()
            self.assertTrue(out["ok"])
            self.assertEqual(out["backend"], "fake")


if __name__ == "__main__":
    unittest.main()
