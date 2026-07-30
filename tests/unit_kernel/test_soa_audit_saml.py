"""ADR-041: auditor-signed SoA + SAML SP tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.auth.saml_sp import (
    SamlServiceProvider,
    SamlSpConfig,
    build_saml_sp,
)
from adapters.compliance.soa import SoaConfig, SoaDraft
from adapters.compliance.soa_audit import (
    FakeSigner,
    SoaAuditConfig,
    SoaAuditor,
    build_soa_auditor,
)


class SoaAuditTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SoaAuditConfig.from_mapping({}).enabled)
        self.assertIsNone(build_soa_auditor({}))

    def test_sign_and_verify_fake(self):
        draft = SoaDraft(cfg=SoaConfig(enabled=True, org_name="Lab"))
        auditor = SoaAuditor(
            cfg=SoaAuditConfig(enabled=True, backend="fake", allow_write=False),
            signer=FakeSigner(signer_id="qa@test"),
            soa=draft,
        )
        envelope = auditor.sign()
        self.assertFalse(envelope["certification"])
        self.assertIn("signature", envelope)
        verified = auditor.verify()
        self.assertTrue(verified["ok"])
        with tempfile.TemporaryDirectory() as td:
            writable = SoaAuditor(
                cfg=SoaAuditConfig(
                    enabled=True,
                    allow_write=True,
                    output_dir=td,
                    signer_id="qa@test",
                ),
                signer=FakeSigner(signer_id="qa@test"),
                soa=draft,
            )
            out = writable.sign()
            self.assertTrue(Path(out["path"]).is_file())
            self.assertTrue(writable.verify()["ok"])


class SamlSpTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SamlSpConfig.from_mapping({}).enabled)
        self.assertIsNone(build_saml_sp({}))

    def test_login_and_acs_fake(self):
        sp = SamlServiceProvider(cfg=SamlSpConfig(enabled=True))
        meta = sp.metadata_xml()
        self.assertIn("EntityDescriptor", meta)
        begin = sp.begin_login(relay_state="/home")
        self.assertIn("redirect_url", begin)
        done = sp.consume(name_id="alice", request_id=begin["request_id"])
        self.assertTrue(done["ok"])
        sess = sp.get_session(done["session"]["session_id"])
        self.assertIsNotNone(sess)
        self.assertEqual(sess["name_id"], "alice")
        self.assertEqual(sp.stats()["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
