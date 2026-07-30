"""ADR-032: Supercluster control-plane + ACME newAccount/cloud DNS tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.acme_account import AcmeAccountConfig, AcmeAccountRegistry
from runtime.acme_cloud_dns import (
    AcmeCloudDnsConfig,
    FakeCloudDnsProvider,
    WebhookCloudDnsProvider,
    build_acme_dns01_with_cloud,
    build_cloud_dns_provider,
)
from runtime.acme_dns01 import dns01_txt_value
from runtime.acme_new_account import (
    AcmeNewAccountClient,
    AcmeNewAccountConfig,
    FakeAcmeDirectoryTransport,
    build_acme_new_account_client,
)
from runtime.nats_supercluster import SuperclusterConfig, SuperclusterTopology
from runtime.nats_supercluster_control import (
    InMemoryControlPlaneBackend,
    SuperclusterControlConfig,
    SuperclusterControlPlane,
    build_supercluster_control_plane,
)
from runtime.nats_supercluster_ops import SuperclusterOps, SuperclusterOpsConfig


def _ops() -> SuperclusterOps:
    topo = SuperclusterTopology.from_config(
        SuperclusterConfig(
            enabled=True,
            name="lab",
            clusters=[
                {"name": "east", "urls": ["nats://east:4222"]},
                {"name": "west", "urls": ["nats://west:4222"]},
            ],
            gateways=[{"from": "east", "to": "west", "gateway_url": "nats://gw:7222"}],
            leafnodes=[{"name": "edge", "urls": ["nats://edge:7422"]}],
        )
    )
    return SuperclusterOps(
        cfg=SuperclusterOpsConfig(enabled=True),
        topology=topo,
    )


class SuperclusterControlPlaneTest(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(SuperclusterControlConfig.from_mapping({}).enabled)
        self.assertIsNone(build_supercluster_control_plane({}))

    def test_publish_config_memory_backend(self):
        ops = _ops()
        ops.plan()
        backend = InMemoryControlPlaneBackend()
        cp = SuperclusterControlPlane(
            cfg=SuperclusterControlConfig(enabled=True, backend="memory", allow_write=True),
            ops=ops,
            backend=backend,
        )
        out = cp.publish_config()
        self.assertTrue(out["ok"])
        self.assertTrue(str(out["path"]).startswith("mem://"))
        self.assertIn("lab", backend.list_configs())
        mon = cp.probe_monitors()
        self.assertTrue(mon[0].get("skipped"))
        sig = cp.maybe_signal_reload()
        self.assertTrue(sig.get("skipped"))
        self.assertEqual(cp.stats()["writes"], 1)

    def test_signal_reload_records_ledger(self):
        backend = InMemoryControlPlaneBackend()
        cp = SuperclusterControlPlane(
            cfg=SuperclusterControlConfig(
                enabled=True, allow_signal_reload=True, backend="memory"
            ),
            backend=backend,
        )
        out = cp.maybe_signal_reload(pid="1")
        self.assertIn("ledger", out)
        self.assertTrue(out["ledger"]["ok"])
        self.assertEqual(backend.stats()["reloads"], 1)


class AcmeNewAccountTest(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(AcmeNewAccountConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_new_account_client({}))

    def test_fake_submit_persists_kid(self):
        with tempfile.TemporaryDirectory() as td:
            reg = AcmeAccountRegistry(
                cfg=AcmeAccountConfig(
                    enabled=True,
                    account_dir=td,
                    contact_email="ops@example.com",
                    dry_run=True,
                )
            )
            client = AcmeNewAccountClient(
                cfg=AcmeNewAccountConfig(enabled=True, allow_live=True, transport="fake"),
                account=reg,
                transport=FakeAcmeDirectoryTransport(),
            )
            out = client.submit()
            self.assertTrue(out["ok"])
            self.assertTrue(str(out["kid"]).startswith("https://"))
            self.assertTrue((Path(td) / "account.json").is_file())
            self.assertEqual(reg.load()["kid"], out["kid"])


class AcmeCloudDnsTest(unittest.TestCase):
    def test_config_default_off(self):
        self.assertFalse(AcmeCloudDnsConfig.from_mapping({}).enabled)
        self.assertIsNone(build_cloud_dns_provider({}))

    def test_fake_cloud_roundtrip_via_dns01(self):
        solver = build_acme_dns01_with_cloud(
            {
                "enabled": True,
                "provider": "fake",
                "cloud": {"enabled": True, "provider": "fake", "zone": "example.com"},
            }
        )
        self.assertIsNotNone(solver)
        assert solver is not None
        key_auth = "tok.thumb"
        put = solver.put_challenge("example.com", key_auth)
        self.assertEqual(put["value"], dns01_txt_value(key_auth))
        self.assertTrue(solver.verify_local("example.com", key_auth))
        self.assertIsInstance(solver.provider, FakeCloudDnsProvider)

    def test_webhook_dry_run_shadows_locally(self):
        prov = WebhookCloudDnsProvider(
            webhook_url="http://127.0.0.1:9/dns",
            allow_live=False,
        )
        prov.upsert_txt("_acme-challenge.example.com", "abc")
        self.assertEqual(prov.get_txt("_acme-challenge.example.com"), ["abc"])
        self.assertTrue(prov.stats()["last"].get("dry_run"))
        prov.delete_txt("_acme-challenge.example.com")
        self.assertEqual(prov.get_txt("_acme-challenge.example.com"), [])


if __name__ == "__main__":
    unittest.main()
