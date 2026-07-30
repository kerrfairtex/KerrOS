"""ADR-047: Helm images + vendor-issued + public mirror + ISO + HSM tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.auth.hsm_xmlsec import (
    FakeHsmToken,
    HsmXmlsecConfig,
    HsmXmlsecService,
    build_hsm_xmlsec,
)
from adapters.compliance.iso_certificate import (
    IsoCertificateConfig,
    IsoCertificateService,
    build_iso_certificate,
)
from runtime.cmdb_vendor_issued import (
    VendorIssuedConfig,
    VendorIssuedRegistry,
    build_vendor_issued,
)
from runtime.distro_public_mirror import (
    PublicMirrorConfig,
    PublicMirrorPublisher,
    build_public_mirror,
)
from runtime.k8s_helm_images import (
    HelmImageConfig,
    HelmImagePublisher,
    build_helm_images,
)


class HelmImagesTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(HelmImageConfig.from_mapping({}).enabled)
        self.assertIsNone(build_helm_images({}))

    def test_write_chart_and_fake_package(self):
        with tempfile.TemporaryDirectory() as td:
            pub = HelmImagePublisher(
                cfg=HelmImageConfig(
                    enabled=True,
                    chart_dir=str(Path(td) / "chart"),
                    allow_write=True,
                    allow_package=False,
                )
            )
            written = pub.write_chart()
            self.assertTrue(written["ok"])
            self.assertTrue((Path(td) / "chart" / "Chart.yaml").is_file())
            pkg = pub.package()
            self.assertTrue(pkg.get("dry_run"))
            push = pub.push()
            self.assertTrue(push.get("dry_run"))


class VendorIssuedTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(VendorIssuedConfig.from_mapping({}).enabled)
        self.assertIsNone(build_vendor_issued({}))

    def test_issue_fake(self):
        reg = VendorIssuedRegistry(cfg=VendorIssuedConfig(enabled=True))
        out = reg.issue("servicenow-tech-partner")
        self.assertFalse(out["vendor_sealed"])
        self.assertFalse(out["certificate"]["vendor_sealed"])


class PublicMirrorTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(PublicMirrorConfig.from_mapping({}).enabled)
        self.assertIsNone(build_public_mirror({}))

    def test_stage_and_gated_public(self):
        with tempfile.TemporaryDirectory() as td:
            pub = PublicMirrorPublisher(
                cfg=PublicMirrorConfig(
                    enabled=True,
                    staging_dir=td,
                    public_url="rsync://public.test/kerros/",
                    allow_write=True,
                    allow_public=False,
                )
            )
            staged = pub.stage()
            self.assertTrue(staged["ok"])
            out = pub.publish()
            self.assertTrue(out.get("dry_run"))
            self.assertFalse(out.get("public"))


class IsoCertificateTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(IsoCertificateConfig.from_mapping({}).enabled)
        self.assertIsNone(build_iso_certificate({}))

    def test_issue_never_silent_accredited(self):
        svc = IsoCertificateService(
            cfg=IsoCertificateConfig(enabled=True, allow_accredited=True)
        )
        out = svc.issue()
        self.assertFalse(out["certification"])
        self.assertFalse(out["iso_accredited"])  # no live CAB confirm


class HsmXmlsecTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(HsmXmlsecConfig.from_mapping({}).enabled)
        self.assertIsNone(build_hsm_xmlsec({}))

    def test_sign_with_fake_hsm(self):
        svc = HsmXmlsecService(
            cfg=HsmXmlsecConfig(enabled=True, allow_hsm=True, allow_encryption=True),
            hsm=FakeHsmToken(),
        )
        xml = "<Assertion><Subject>alice</Subject></Assertion>"
        sig = svc.sign(xml)
        self.assertTrue(sig["hsm"])
        self.assertIn("hsm_signature", sig)
        self.assertFalse(sig["production"])
        self.assertTrue(svc.verify(xml, sig)["ok"])


if __name__ == "__main__":
    unittest.main()
