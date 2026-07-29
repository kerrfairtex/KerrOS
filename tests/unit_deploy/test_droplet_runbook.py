"""Droplet runbook artifacts for README §7 #2."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "DROPLET_RUNBOOK.md"
SCRIPT = ROOT / "scripts" / "omniroute_droplet.sh"
DEPLOY_README = ROOT / "deploy" / "omniroute" / "README.md"


class DropletRunbookTest(unittest.TestCase):
    def test_runbook_exists_with_required_sections(self):
        self.assertTrue(RUNBOOK.is_file())
        text = RUNBOOK.read_text(encoding="utf-8")
        for needle in (
            "Re-provision the droplet",
            "Install Docker",
            "STORAGE_ENCRYPTION_KEY",
            "127.0.0.1:20128",
            "omniroute_droplet.sh verify",
            "MEMORY_SEPARATION",
            "Done criteria",
        ):
            self.assertIn(needle, text, msg=f"missing {needle!r}")

    def test_deploy_readme_links_runbook(self):
        text = DEPLOY_README.read_text(encoding="utf-8")
        self.assertIn("DROPLET_RUNBOOK.md", text)
        self.assertIn("verify", text)

    def test_script_documents_doctor_and_verify(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("cmd_doctor", text)
        self.assertIn("cmd_verify", text)
        self.assertIn("DROPLET_RUNBOOK.md", text)

    def test_script_check_still_passes(self):
        proc = subprocess.run(
            ["bash", str(SCRIPT), "check"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("loopback OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
