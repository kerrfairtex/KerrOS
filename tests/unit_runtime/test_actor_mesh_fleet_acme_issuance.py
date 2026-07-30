"""ADR-035: broker fleet + ACME issuance tests."""

from __future__ import annotations

import unittest

from runtime.acme_issuance import (
    AcmeIssuanceClient,
    AcmeIssuanceConfig,
    FakeChallengeSolver,
    build_acme_issuance_client,
)
from runtime.acme_jose import AcmeJoseConfig, AcmeOrderClient, FakeJoseSigner
from runtime.nats_broker_fleet import (
    BrokerFleet,
    BrokerFleetConfig,
    build_broker_fleet,
)
from runtime.nats_broker_lifecycle import (
    BrokerLifecycleConfig,
    InMemoryBrokerProcess,
    NatsBrokerLifecycle,
)


class BrokerFleetTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(BrokerFleetConfig.from_mapping({}).enabled)
        self.assertIsNone(build_broker_fleet({}))

    def test_start_stop_health(self):
        fleet = BrokerFleet(cfg=BrokerFleetConfig(enabled=True, backend="memory"))
        fleet.add_member(
            "east",
            lifecycle=NatsBrokerLifecycle(
                cfg=BrokerLifecycleConfig(enabled=True),
                backend=InMemoryBrokerProcess(name="east"),
            ),
            region="us-east",
        )
        fleet.add_member(
            "west",
            lifecycle=NatsBrokerLifecycle(
                cfg=BrokerLifecycleConfig(enabled=True),
                backend=InMemoryBrokerProcess(name="west"),
            ),
            region="us-west",
        )
        out = fleet.start_all()
        self.assertTrue(out["ok"])
        health = fleet.health()
        self.assertEqual(health["running"], 2)
        self.assertTrue(health["healthy"])
        fleet.stop_all()
        self.assertEqual(fleet.health()["running"], 0)


class AcmeIssuanceTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(AcmeIssuanceConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_issuance_client({}))

    def test_fake_issue_pipeline(self):
        orders = AcmeOrderClient(
            cfg=AcmeJoseConfig(enabled=True),
            signer=FakeJoseSigner(),
        )
        client = AcmeIssuanceClient(
            cfg=AcmeIssuanceConfig(enabled=True, challenge="dns-01"),
            order_client=orders,
            solver=FakeChallengeSolver(kind="dns-01"),
        )
        result = client.issue(["example.com", "www.example.com"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["fake"])
        self.assertIn("BEGIN CERTIFICATE", result["certificate_pem"])
        self.assertEqual(len(result["challenges"]), 2)
        self.assertEqual(client.stats()["issued"], 1)

    def test_live_skipped(self):
        client = build_acme_issuance_client(
            {"enabled": True, "allow_live": True}
        )
        assert client is not None
        out = client.issue(["example.com"])
        self.assertTrue(out.get("skipped_live"))


if __name__ == "__main__":
    unittest.main()
