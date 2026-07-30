"""ADR-037: remote fleet orchestration + packaged production ACME tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.acme_production import (
    AcmeProductionClient,
    AcmeProductionConfig,
    FakePackagedAcme,
    SoftCertbotRunner,
    build_acme_production_client,
)
from runtime.nats_remote_fleet import (
    FakeRemoteAgentTransport,
    HttpRemoteAgentTransport,
    RemoteFleetConfig,
    RemoteFleetOrchestrator,
    build_remote_fleet_orchestrator,
)


class RemoteFleetTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(RemoteFleetConfig.from_mapping({}).enabled)
        self.assertIsNone(build_remote_fleet_orchestrator({}))

    def test_plan_apply_fake(self):
        orch = RemoteFleetOrchestrator(
            cfg=RemoteFleetConfig(
                enabled=True,
                transport="fake",
                hosts=[
                    {"name": "east", "host": "east.example", "members": ["nats-a", "nats-b"]},
                    {"name": "west", "host": "west.example", "members": ["nats-a"]},
                ],
            ),
            transport=FakeRemoteAgentTransport(),
        )
        plan = orch.plan("start")
        self.assertEqual(len(plan), 3)
        out = orch.apply("start")
        self.assertTrue(out["ok"])
        self.assertEqual(len(out["results"]), 3)
        status = orch.status_all()
        self.assertTrue(status["ok"])
        self.assertEqual(orch.stats()["hosts"], 2)

    def test_http_dry_run(self):
        tr = HttpRemoteAgentTransport(
            base_url="http://127.0.0.1:9", allow_live=False
        )
        out = tr.exec_action("h1", "start", member="broker")
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("dry_run"))


class AcmeProductionTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(AcmeProductionConfig.from_mapping({}).enabled)
        self.assertIsNone(build_acme_production_client({}))

    def test_fake_writes_live_dir(self):
        with tempfile.TemporaryDirectory() as td:
            live = Path(td) / "live"
            client = AcmeProductionClient(
                cfg=AcmeProductionConfig(
                    enabled=True,
                    tool="fake",
                    domains=["example.com"],
                    live_dir=str(live),
                ),
                runner=FakePackagedAcme(),
            )
            out = client.issue()
            self.assertTrue(out["ok"])
            self.assertTrue(Path(out["fullchain"]).is_file())
            self.assertTrue(str(out["live_dir"]).endswith("example.com"))
            self.assertTrue((live / "example.com" / "privkey.pem").is_file())

    def test_certbot_dry_run_shadow(self):
        with tempfile.TemporaryDirectory() as td:
            runner = SoftCertbotRunner(allow_live=False)
            out = runner.issue(["ex.com"], live_dir=str(Path(td) / "live"))
            self.assertTrue(out["ok"])
            self.assertTrue(out.get("dry_run") or out.get("fake"))


if __name__ == "__main__":
    unittest.main()
