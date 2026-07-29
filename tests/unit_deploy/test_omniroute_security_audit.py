"""§6 OmniRoute security audit static guards."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check_omniroute_security.py"


class OmniRouteSecurityAuditTest(unittest.TestCase):
    def test_check_script_passes(self):
        proc = subprocess.run(
            [sys.executable, str(CHECK)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=proc.stdout + "\n" + proc.stderr,
        )
        self.assertIn("OK:", proc.stdout)

    def test_audit_doc_exists(self):
        doc = ROOT / "docs" / "OMNIROUTE_SECURITY_AUDIT.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("AES-256-GCM", text)
        self.assertIn("promptfoo", text)
        self.assertIn("127.0.0.1", text)

    def test_fixtures_cover_poison_cases(self):
        import json

        path = (
            ROOT
            / "eval"
            / "omniroute_rag_promptfoo"
            / "fixtures"
            / "rag_injected_prompts.json"
        )
        cases = json.loads(path.read_text(encoding="utf-8"))
        ids = {c["id"] for c in cases}
        self.assertIn("poison_ignore_instructions", ids)
        self.assertIn("poison_exfiltrate_env", ids)
        self.assertGreaterEqual(len(cases), 5)


if __name__ == "__main__":
    unittest.main()
