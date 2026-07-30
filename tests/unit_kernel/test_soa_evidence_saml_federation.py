"""ADR-044: auditor evidence packs + SAML federation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.auth.saml_federation import (
    IdpFederationEntry,
    SamlFederation,
    SamlFederationConfig,
    build_saml_federation,
    xmlsec_available,
)
from adapters.compliance.soa_evidence import (
    SoaEvidenceConfig,
    SoaEvidencePack,
    build_soa_evidence,
)


class SoaEvidenceTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SoaEvidenceConfig.from_mapping({}).enabled)
        self.assertIsNone(build_soa_evidence({}))

    def test_assemble_memory_and_write(self):
        pack = SoaEvidencePack(
            cfg=SoaEvidenceConfig(enabled=True, org_name="Lab", allow_write=False)
        )
        out = pack.assemble()
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("skipped_write"))
        self.assertFalse(out["pack"]["certification"])
        self.assertIn("residual_risks", out["pack"]["manifest"])
        with tempfile.TemporaryDirectory() as td:
            writable = SoaEvidencePack(
                cfg=SoaEvidenceConfig(
                    enabled=True,
                    org_name="Lab",
                    output_dir=td + "/evidence",
                    allow_write=True,
                    allow_zip=True,
                )
            )
            written = writable.assemble()
            self.assertTrue(written["ok"])
            self.assertTrue(Path(written["dir"]).is_dir())
            self.assertTrue(Path(written["zip"]).is_file())
            self.assertTrue((Path(written["dir"]) / "manifest.json").is_file())


class SamlFederationTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SamlFederationConfig.from_mapping({}).enabled)
        self.assertIsNone(build_saml_federation({}))

    def test_multi_idp_login_and_acs(self):
        fed = SamlFederation(
            cfg=SamlFederationConfig(enabled=True, require_signed_assertions=True),
            idps=[
                IdpFederationEntry(
                    entity_id="https://idp-a.test/saml",
                    sso_url="https://idp-a.test/sso",
                    display_name="A",
                ),
                IdpFederationEntry(
                    entity_id="https://idp-b.test/saml",
                    sso_url="https://idp-b.test/sso",
                    display_name="B",
                ),
            ],
        )
        self.assertEqual(len(fed.list_idps()), 2)
        meta = fed.metadata_xml()
        self.assertIn("WantAssertionsSigned", meta)
        begin = fed.begin_login(idp_entity_id="https://idp-b.test/saml")
        self.assertEqual(begin["idp"], "https://idp-b.test/saml")
        done = fed.consume(
            idp_entity_id="https://idp-b.test/saml",
            name_id="bob",
            request_id=begin["request_id"],
        )
        self.assertTrue(done["ok"])
        self.assertFalse(done["production"])
        self.assertEqual(done["session"]["idp"], "https://idp-b.test/saml")
        self.assertIsInstance(xmlsec_available(), bool)

    def test_encrypted_gate(self):
        fed = SamlFederation(
            cfg=SamlFederationConfig(
                enabled=True, allow_encrypted_assertions=False
            ),
            idps=[
                IdpFederationEntry(
                    entity_id="https://idp.test/saml",
                    sso_url="https://idp.test/sso",
                )
            ],
        )
        with self.assertRaises(Exception):
            fed.consume(name_id="x", encrypted=True)


if __name__ == "__main__":
    unittest.main()
