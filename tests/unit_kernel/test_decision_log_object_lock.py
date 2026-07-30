"""ADR-022: Object Lock / compliance mirror tests (no network)."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adapters.audit.object_lock import (
    ObjectLockConfig,
    ObjectLockError,
    mirror_after_seal,
    mirror_local,
    mirror_s3,
    object_lock_config_from,
)
from adapters.audit.worm_store import WormStore
from kernel.decision_log import DecisionLog


class ObjectLockConfigTest(unittest.TestCase):
    def test_defaults_disabled(self):
        cfg = object_lock_config_from({})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.backend, "local_mirror")

    def test_env_enable(self):
        with patch.dict(
            "os.environ",
            {
                "KERROS_AUDIT_OBJECT_LOCK": "1",
                "KERROS_AUDIT_OBJECT_LOCK_BACKEND": "s3_object_lock",
                "KERROS_AUDIT_OBJECT_LOCK_BUCKET": "ev",
            },
            clear=False,
        ):
            cfg = object_lock_config_from({})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.backend, "s3_object_lock")
        self.assertEqual(cfg.bucket, "ev")


class LocalMirrorTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db = self.root / "d.db"
        self.worm = self.root / "worm"
        self.mirror = self.root / "mirror"
        self.log = DecisionLog(self.db)
        self.log.record("a", "t", "one", "ok", "", timestamp=1.0)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_disabled_noop(self):
        store = WormStore(self.worm)
        with patch(
            "adapters.audit.object_lock.object_lock_config_from",
            return_value=ObjectLockConfig(enabled=False),
        ):
            out = store.seal_from_log(self.log, through_id=1, skip_rbac=True)
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("object_lock", {}).get("skipped"))

    def test_local_mirror_readonly(self):
        store = WormStore(self.worm)
        cfg = {
            "audit_object_lock": {
                "enabled": True,
                "backend": "local_mirror",
                "mirror_dir": str(self.mirror),
                "strict": False,
            }
        }
        with patch("kernel.config.load_config") as load:
            load.return_value.values = cfg
            load.return_value.base = self.root
            out = store.seal_from_log(self.log, through_id=1, skip_rbac=True)
        self.assertTrue(out["ok"])
        ol = out.get("object_lock") or {}
        self.assertTrue(ol.get("ok"))
        mirrored = Path(ol["jsonl"])
        self.assertTrue(mirrored.is_file())
        self.assertFalse(mirrored.stat().st_mode & stat.S_IWUSR)
        with self.assertRaises(ObjectLockError):
            mirror_local(
                Path(out["path"]), Path(out["manifest"]), self.mirror
            )

    def test_s3_mock_put(self):
        jsonl = self.root / "000001.jsonl"
        manifest = self.root / "000001.manifest.json"
        jsonl.write_text("{}\n", encoding="utf-8")
        manifest.write_text("{}\n", encoding="utf-8")
        client = MagicMock()
        cfg = ObjectLockConfig(
            enabled=True,
            backend="s3_object_lock",
            bucket="audit-bucket",
            prefix="kerros/",
            retain_days=30,
            object_lock_mode="GOVERNANCE",
        )
        out = mirror_s3(jsonl, manifest, cfg, client=client)
        self.assertTrue(out["ok"])
        self.assertEqual(client.put_object.call_count, 2)
        kwargs = client.put_object.call_args_list[0].kwargs
        self.assertEqual(kwargs["Bucket"], "audit-bucket")
        self.assertEqual(kwargs["ObjectLockMode"], "GOVERNANCE")
        self.assertIn("ObjectLockRetainUntilDate", kwargs)

    def test_missing_boto_nonstrict(self):
        store = WormStore(self.worm)
        cfg = {
            "audit_object_lock": {
                "enabled": True,
                "backend": "s3_object_lock",
                "bucket": "b",
                "strict": False,
            }
        }

        def _raise_import(*_a, **_k):
            raise ObjectLockError("requires boto3")

        with patch("kernel.config.load_config") as load:
            load.return_value.values = cfg
            load.return_value.base = self.root
            with patch(
                "adapters.audit.object_lock._build_boto_client",
                side_effect=_raise_import,
            ):
                out = store.seal_from_log(self.log, through_id=1, skip_rbac=True)
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("object_lock", {}).get("skipped"))

    def test_missing_boto_strict_fails_seal(self):
        store = WormStore(self.worm)
        cfg = {
            "audit_object_lock": {
                "enabled": True,
                "backend": "s3_object_lock",
                "bucket": "b",
                "strict": True,
            }
        }
        with patch("kernel.config.load_config") as load:
            load.return_value.values = cfg
            load.return_value.base = self.root
            with patch(
                "adapters.audit.object_lock._build_boto_client",
                side_effect=ObjectLockError("requires boto3"),
            ):
                with self.assertRaises(Exception):
                    store.seal_from_log(self.log, through_id=1, skip_rbac=True)

    def test_mirror_after_seal_helper(self):
        store = WormStore(self.worm)
        sealed = store.seal_from_log(self.log, through_id=1, skip_rbac=True)
        cfg = {
            "audit_object_lock": {
                "enabled": True,
                "backend": "local_mirror",
                "mirror_dir": str(self.mirror),
            }
        }
        out = mirror_after_seal(sealed, cfg=cfg, base=self.root)
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
