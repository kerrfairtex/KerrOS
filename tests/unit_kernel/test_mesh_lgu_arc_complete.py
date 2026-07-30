"""ADR-046: mesh/LGU foundation arc complete — documentation guard."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MeshLguArcCompleteTest(unittest.TestCase):
    def test_adr_046_declares_complete(self):
        adr = ROOT / "docs" / "adr" / "ADR-046-mesh-lgu-foundation-arc-complete.md"
        self.assertTrue(adr.is_file())
        text = adr.read_text(encoding="utf-8")
        self.assertIn("foundation arc complete", text.lower())
        self.assertIn("contract-only", text.lower())
        self.assertIn("ADR-045", text)

    def test_decision_doc_lists_contract_only(self):
        doc = ROOT / "docs" / "decisions" / "mesh-lgu-foundation-arc.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("Contract-only", text)
        self.assertIn("HSM-backed xmlsec", text)
        self.assertIn("Accredited ISO", text)

    def test_phase2_deferred_points_at_arc(self):
        phase2 = (ROOT / "docs" / "PHASE2.md").read_text(encoding="utf-8")
        self.assertIn("ADR-046", phase2)
        self.assertIn("contract-only", phase2)


if __name__ == "__main__":
    unittest.main()
