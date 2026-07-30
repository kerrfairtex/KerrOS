"""ADR-034: hardware WORM + crypto-shred + IdP portal tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.audit.crypto_shred import (
    CryptoShredConfig,
    CryptoShredError,
    CryptoShredKeyStore,
    build_crypto_shred_store,
)
from adapters.audit.hardware_worm import (
    FakeHardwareWormAppliance,
    HardwareWormConfig,
    HardwareWormError,
    HardwareWormMirror,
    build_hardware_worm_mirror,
)
from adapters.auth.idp_portal import (
    DataSubjectPortal,
    IdpPortalConfig,
    build_idp_portal,
)


class HardwareWormTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(HardwareWormConfig.from_mapping({}).enabled)
        self.assertIsNone(build_hardware_worm_mirror({}))

    def test_fake_refuse_overwrite_and_mirror(self):
        app = FakeHardwareWormAppliance()
        app.put_object("a.bin", b"one")
        with self.assertRaises(HardwareWormError):
            app.put_object("a.bin", b"two")
        with tempfile.TemporaryDirectory() as td:
            seg = Path(td) / "000001.jsonl"
            seg.write_bytes(b'{"x":1}\n')
            mirror = HardwareWormMirror(
                cfg=HardwareWormConfig(enabled=True, backend="fake", prefix="worm/"),
                appliance=app,
            )
            out = mirror.mirror_segment(seg, segment=1)
            self.assertTrue(out["ok"])
            self.assertIsNotNone(app.head_object("worm/000001.jsonl"))


class CryptoShredTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(CryptoShredConfig.from_mapping({}).enabled)
        self.assertIsNone(build_crypto_shred_store({}))

    def test_encrypt_shred_blocks_decrypt(self):
        with tempfile.TemporaryDirectory() as td:
            store = CryptoShredKeyStore(
                cfg=CryptoShredConfig(
                    enabled=True,
                    db_path=str(Path(td) / "keys.db"),
                    allow_shred=True,
                )
            )
            minted = store.mint_dek("subject-1")
            kid = minted["key_id"]
            ct = store.encrypt(kid, b"secret-bytes")
            self.assertEqual(store.decrypt(kid, ct), b"secret-bytes")
            shredded = store.shred(kid, actor="admin", note="dsar")
            self.assertTrue(shredded["worm_untouched"])
            with self.assertRaises(CryptoShredError):
                store.decrypt(kid, ct)
            self.assertEqual(store.stats()["shredded_deks"], 1)

    def test_shred_gated(self):
        with tempfile.TemporaryDirectory() as td:
            store = CryptoShredKeyStore(
                cfg=CryptoShredConfig(
                    enabled=True,
                    db_path=str(Path(td) / "keys.db"),
                    allow_shred=False,
                )
            )
            kid = store.mint_dek("s")["key_id"]
            with self.assertRaises(CryptoShredError):
                store.shred(kid)


class IdpPortalTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(IdpPortalConfig.from_mapping({}).enabled)
        self.assertIsNone(build_idp_portal({}))

    def test_login_access_erasure_hook(self):
        calls: list[tuple[str, str]] = []

        def hook(subject: str, reason: str) -> dict:
            calls.append((subject, reason))
            return {"ok": True, "status": "recorded"}

        portal = DataSubjectPortal(
            cfg=IdpPortalConfig(enabled=True, backend="fake"),
            erasure_hook=hook,
        )
        sess = portal.login("user-1", email="u@example.com")
        access = portal.request_access(sess["session_id"])
        self.assertEqual(access["type"], "access")
        erasure = portal.request_erasure(sess["session_id"], reason="dsar")
        self.assertEqual(erasure["type"], "erasure")
        self.assertEqual(calls, [("user-1", "dsar")])
        disc = portal.maybe_discover()
        self.assertTrue(disc.get("skipped") or disc.get("ok"))


if __name__ == "__main__":
    unittest.main()
