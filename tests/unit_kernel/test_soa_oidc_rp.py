"""ADR-036: SoA draft + OIDC RP tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.auth.oidc_rp import (
    OidcRelyingParty,
    OidcRpConfig,
    build_oidc_rp,
)
from adapters.compliance.soa import (
    SoaConfig,
    SoaDraft,
    build_soa_draft,
)


class SoaDraftTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(SoaConfig.from_mapping({}).enabled)
        self.assertIsNone(build_soa_draft({}))

    def test_build_and_optional_write(self):
        draft = SoaDraft(cfg=SoaConfig(enabled=True, org_name="Lab", allow_write=False))
        doc = draft.build()
        self.assertFalse(doc["certification"])
        self.assertGreaterEqual(len(doc["controls"]), 5)
        skipped = draft.write_json()
        self.assertTrue(skipped.get("skipped"))
        with tempfile.TemporaryDirectory() as td:
            writable = SoaDraft(
                cfg=SoaConfig(
                    enabled=True,
                    org_name="Lab",
                    output_dir=td,
                    allow_write=True,
                )
            )
            out = writable.write_json()
            self.assertTrue(out["ok"])
            self.assertTrue(Path(out["path"]).is_file())


class OidcRpTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(OidcRpConfig.from_mapping({}).enabled)
        self.assertIsNone(build_oidc_rp({}))

    def test_auth_code_flow_fake(self):
        rp = OidcRelyingParty(
            cfg=OidcRpConfig(enabled=True, issuer="https://idp.test")
        )
        begin = rp.begin_auth(subject_hint="alice")
        self.assertIn("authorization_url", begin)
        self.assertIn("state", begin)
        done = rp.complete_auth(state=begin["state"], subject_id="alice")
        self.assertTrue(done["ok"])
        self.assertEqual(done["subject_id"], "alice")
        sess = rp.get_session(done["session_id"])
        self.assertIsNotNone(sess)
        self.assertEqual(rp.stats()["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
