"""ADR-021: decision_log RBAC + SIEM forwarder tests."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from adapters.audit.decision_log_export import export_decision_log_jsonl
from adapters.audit.rbac import AuditRbac, AuditRbacError, audit_rbac_from_config
from adapters.audit.retention import apply_retention
from adapters.audit.siem_forwarder import SiemForwarder, reset_siem_forwarder
from adapters.audit.worm_store import WormStore
from kernel.decision_log import DecisionLog


class _CaptureHandler(BaseHTTPRequestHandler):
    bodies: list[bytes] = []

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        _CaptureHandler.bodies.append(self.rfile.read(length))
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


class AuditRbacTest(unittest.TestCase):
    def setUp(self):
        self.rbac = AuditRbac(
            enabled=True,
            tokens={
                "tok-reader": "reader",
                "tok-ops": "operator",
                "tok-admin": "admin",
            },
        )

    def test_disabled_allows_all(self):
        open_rbac = AuditRbac(enabled=False, tokens={})
        self.assertEqual(open_rbac.check("purge", token=None), "open")

    def test_reader_limits(self):
        self.assertEqual(self.rbac.check("read", token="tok-reader"), "reader")
        self.assertEqual(self.rbac.check("verify", token="tok-reader"), "reader")
        with self.assertRaises(AuditRbacError):
            self.rbac.check("export", token="tok-reader")
        with self.assertRaises(AuditRbacError):
            self.rbac.check("seal", token="tok-reader")

    def test_operator_and_admin(self):
        self.assertEqual(self.rbac.check("export", token="tok-ops"), "operator")
        self.assertEqual(self.rbac.check("seal", token="tok-ops"), "operator")
        with self.assertRaises(AuditRbacError):
            self.rbac.check("retain", token="tok-ops")
        self.assertEqual(self.rbac.check("purge", token="tok-admin"), "admin")

    def test_bad_token(self):
        with self.assertRaises(AuditRbacError):
            self.rbac.check("read", token="nope")

    def test_from_config_env_tokens(self):
        with patch.dict(
            "os.environ",
            {
                "KERROS_AUDIT_RBAC": "1",
                "KERROS_AUDIT_RBAC_TOKENS": "a=reader,b=admin",
            },
            clear=False,
        ):
            rbac = audit_rbac_from_config({})
        self.assertTrue(rbac.enabled)
        self.assertEqual(rbac.check("read", token="a"), "reader")


class AuditSiemTest(unittest.TestCase):
    def setUp(self):
        reset_siem_forwarder()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Path(self._tmpdir.name) / "d.db"
        self.log = DecisionLog(self.db)
        _CaptureHandler.bodies = []

    def tearDown(self):
        reset_siem_forwarder()
        self._tmpdir.cleanup()

    def test_disabled_record_no_http(self):
        fwd = SiemForwarder(enabled=False, url="http://127.0.0.1:9/x")
        with patch("adapters.audit.siem_forwarder.get_siem_forwarder", return_value=fwd):
            rid = self.log.record("a", "t", "x", "ok", "")
        self.assertGreater(rid, 0)
        self.assertEqual(fwd.stats()["sent"], 0)

    def test_webhook_on_record(self):
        server = HTTPServer(("127.0.0.1", 0), _CaptureHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        fwd = SiemForwarder(
            enabled=True,
            transport="webhook",
            url=f"http://127.0.0.1:{port}/ingest",
            timeout_s=2.0,
        )
        try:
            with patch(
                "adapters.audit.siem_forwarder.get_siem_forwarder", return_value=fwd
            ):
                self.log.record("a", "t", "siem-row", "ok", "", timestamp=1.0)
            self.assertEqual(fwd.stats()["sent"], 1)
            self.assertTrue(_CaptureHandler.bodies)
            payload = json.loads(_CaptureHandler.bodies[0].decode())
            self.assertEqual(payload["event"], "decision_record")
            self.assertEqual(payload["input_summary"], "siem-row")
        finally:
            server.shutdown()

    def test_webhook_failure_still_records(self):
        fwd = SiemForwarder(
            enabled=True,
            url="http://127.0.0.1:1/nope",
            timeout_s=0.2,
        )
        with patch("adapters.audit.siem_forwarder.get_siem_forwarder", return_value=fwd):
            rid = self.log.record("a", "t", "x", "ok", "")
        self.assertGreater(rid, 0)
        self.assertEqual(fwd.stats()["errors"], 1)

    def test_seal_forwards(self):
        self.log.record("a", "t", "one", "ok", "", timestamp=1.0)
        worm = Path(self._tmpdir.name) / "worm"
        fwd = SiemForwarder(enabled=True, url="http://127.0.0.1:1/x", timeout_s=0.1)
        with patch("adapters.audit.siem_forwarder.get_siem_forwarder", return_value=fwd):
            out = WormStore(worm).seal_from_log(
                self.log, through_id=1, skip_rbac=True
            )
        self.assertTrue(out["ok"])
        # failure increments errors but seal still ok
        self.assertEqual(fwd.stats()["errors"], 1)


class AuditRbacIntegrationTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Path(self._tmpdir.name) / "d.db"
        self.log = DecisionLog(self.db)
        self.log.record("a", "t", "r1", "ok", "", timestamp=1.0)
        self.cfg = {
            "audit_rbac": {
                "enabled": True,
                "tokens": {"r": "reader", "o": "operator", "a": "admin"},
            }
        }

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_export_denied_for_reader(self):
        with patch(
            "adapters.audit.rbac.audit_rbac_from_config",
            return_value=AuditRbac(
                enabled=True, tokens={"r": "reader", "o": "operator"}
            ),
        ):
            with self.assertRaises(AuditRbacError):
                export_decision_log_jsonl(
                    Path(self._tmpdir.name) / "out.jsonl",
                    log=self.log,
                    audit_token="r",
                )

    def test_export_ok_for_operator(self):
        with patch(
            "adapters.audit.rbac.audit_rbac_from_config",
            return_value=AuditRbac(
                enabled=True, tokens={"o": "operator"}
            ),
        ):
            out = export_decision_log_jsonl(
                Path(self._tmpdir.name) / "out.jsonl",
                log=self.log,
                audit_token="o",
            )
        self.assertTrue(out["ok"])

    def test_retain_denied_for_operator(self):
        out = apply_retention(
            self.log,
            cfg={
                "audit_rbac": {
                    "enabled": True,
                    "tokens": {"o": "operator"},
                },
                "audit_retention": {
                    "enabled": True,
                    "retain_days": 0,
                    "action": "archive",
                    "worm_dir": str(Path(self._tmpdir.name) / "worm"),
                },
            },
            now=10.0,
            audit_token="o",
        )
        self.assertFalse(out["ok"])
        self.assertIn("RBAC", out["error"])


if __name__ == "__main__":
    unittest.main()
