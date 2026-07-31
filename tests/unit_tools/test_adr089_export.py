"""ADR-089 Soft SIEM trace export."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TraceExportTest(unittest.TestCase):
    def test_json_and_cef_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            tpath = base / "data" / "channel_trace.jsonl"
            with patch("gateway.channels.trace.BASE", base), patch(
                "gateway.channels.trace.TRACE_PATH", tpath
            ):
                from gateway.channels import export as ex
                from gateway.channels import trace as tr

                tr.clear_trace()
                tr.append_trace("exp", {"n": 1})
                out_json = base / "out.json"
                r = ex.export_trace(format="json", path=str(out_json))
                self.assertTrue(r["ok"])
                self.assertTrue(out_json.exists())
                out_cef = base / "out.cef"
                r2 = ex.export_trace(format="cef", path=str(out_cef))
                self.assertTrue(r2["ok"])
                self.assertIn("CEF:0|KerrOS", out_cef.read_text())


if __name__ == "__main__":
    unittest.main()
