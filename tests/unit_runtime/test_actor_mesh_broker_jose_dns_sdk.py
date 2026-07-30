"""ADR-033: broker lifecycle + ACME JOSE + cloud DNS SDK tests."""

from __future__ import annotations

import unittest

from runtime.acme_cloud_dns_sdk import (
    CloudDnsSdkConfig,
    SoftCloudflareDnsProvider,
    SoftRoute53DnsProvider,
    build_cloud_dns_sdk_provider,
)
from runtime.acme_jose import (
    AcmeJoseConfig,
    AcmeOrderClient,
    FakeJoseSigner,
    build_acme_order_client,
    jws_flattened,
)
from runtime.nats_broker_lifecycle import (
    BrokerLifecycleConfig,
    InMemoryBrokerProcess,
    NatsBrokerLifecycle,
    build_nats_broker_lifecycle,
)


class BrokerLifecycleTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(BrokerLifecycleConfig.from_mapping({}).enabled)
        self.assertIsNone(build_nats_broker_lifecycle({}))

    def test_memory_start_stop(self):
        mgr = NatsBrokerLifecycle(
            cfg=BrokerLifecycleConfig(enabled=True, backend="memory"),
            backend=InMemoryBrokerProcess(),
        )
        self.assertTrue(mgr.start()["ok"])
        self.assertTrue(mgr.status()["running"])
        self.assertTrue(mgr.stop()["ok"])
        self.assertFalse(mgr.status()["running"])
        self.assertTrue(mgr.restart()["ok"])
        mgr.stop()


class AcmeJoseTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(AcmeJoseConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_order_client({}))

    def test_jws_and_fake_order(self):
        signer = FakeJoseSigner()
        jws = jws_flattened({"identifiers": [{"type": "dns", "value": "ex.com"}]}, signer=signer)
        self.assertIn("protected", jws)
        self.assertIn("signature", jws)
        client = AcmeOrderClient(
            cfg=AcmeJoseConfig(enabled=True),
            signer=signer,
        )
        order = client.create_order(["example.com"])
        self.assertTrue(order["ok"])
        self.assertEqual(order["status"], "pending")
        self.assertEqual(client.stats()["orders"], 1)


class CloudDnsSdkTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(CloudDnsSdkConfig.from_mapping({}).enabled)
        self.assertIsNone(build_cloud_dns_sdk_provider({}))

    def test_route53_dry_run(self):
        prov = SoftRoute53DnsProvider(hosted_zone_id="Z1", allow_live=False)
        prov.upsert_txt("_acme-challenge.example.com", "v")
        self.assertEqual(prov.get_txt("_acme-challenge.example.com"), ["v"])
        self.assertTrue(prov.stats()["last"].get("dry_run"))

    def test_cloudflare_dry_run(self):
        prov = SoftCloudflareDnsProvider(allow_live=False)
        prov.upsert_txt("_acme-challenge.example.com", "cf")
        self.assertEqual(prov.get_txt("_acme-challenge.example.com"), ["cf"])
        prov.delete_txt("_acme-challenge.example.com")
        self.assertEqual(prov.get_txt("_acme-challenge.example.com"), [])


if __name__ == "__main__":
    unittest.main()
