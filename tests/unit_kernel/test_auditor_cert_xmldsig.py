"""ADR-045: auditor-issued certificates + full XMLDSig tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.auth.xmldsig import (
    FakeXmlDsigEngine,
    XmlDsigConfig,
    XmlDsigService,
    build_xmldsig,
    c14n_fake,
)
from adapters.compliance.auditor_cert import (
    AuditorCertConfig,
    AuditorCertificateService,
    FakeAuditorCa,
    build_auditor_cert,
)
from adapters.compliance.soa_evidence import SoaEvidenceConfig, SoaEvidencePack


class AuditorCertTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(AuditorCertConfig.from_mapping({}).enabled)
        self.assertIsNone(build_auditor_cert({}))

    def test_issue_and_verify(self):
        evidence = SoaEvidencePack(
            cfg=SoaEvidenceConfig(enabled=True, allow_write=False)
        )
        svc = AuditorCertificateService(
            cfg=AuditorCertConfig(enabled=True, allow_write=False, allow_claim=True),
            ca=FakeAuditorCa(ca_name="Test CA"),
            evidence=evidence,
        )
        envelope = svc.issue()
        self.assertFalse(envelope["certification"])
        self.assertFalse(envelope["iso_certified"])
        self.assertIn("certificate", envelope)
        verified = svc.verify(envelope)
        self.assertTrue(verified["ok"])
        with tempfile.TemporaryDirectory() as td:
            writable = AuditorCertificateService(
                cfg=AuditorCertConfig(
                    enabled=True, allow_write=True, output_dir=td
                ),
                ca=FakeAuditorCa(),
                evidence=evidence,
            )
            out = writable.issue()
            self.assertTrue(Path(out["path"]).is_file())
            self.assertTrue(Path(out["pem_path"]).is_file())


class XmlDsigTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(XmlDsigConfig.from_mapping({}).enabled)
        self.assertIsNone(build_xmldsig({}))

    def test_sign_verify_encrypt(self):
        svc = XmlDsigService(
            cfg=XmlDsigConfig(enabled=True, allow_encryption=True),
            engine=FakeXmlDsigEngine(),
        )
        xml = "<Assertion ID='a1'><Subject>alice</Subject></Assertion>"
        sig = svc.sign(xml, reference_uri="#a1")
        self.assertIn("SignedInfo", sig)
        self.assertIn("SignatureValue", sig)
        self.assertFalse(sig["production"])
        self.assertTrue(svc.verify(xml, sig)["ok"])
        # Tamper digest
        bad = dict(sig)
        bad["DigestValue"] = "deadbeef"
        self.assertFalse(svc.verify(xml, bad)["ok"])
        enc = svc.encrypt(xml)
        self.assertIn("EncryptedData", enc)
        dec = svc.decrypt(enc)
        self.assertIn("alice", dec["xml"])
        wrapped = svc.sign_assertion("<Subject>alice</Subject>")
        self.assertIn("Signature", wrapped["signed_xml"])
        self.assertTrue(len(c14n_fake(b"<a>  b  </a>")) < len(b"<a>  b  </a>"))


if __name__ == "__main__":
    unittest.main()
