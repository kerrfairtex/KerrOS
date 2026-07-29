"""Tests for Documentation-as-Code capability renderer."""

import tempfile
import unittest
from pathlib import Path

from scripts.render_capabilities import (
    load_capabilities,
    main,
    render_markdown,
    _normalize_for_compare,
)


class RenderCapabilitiesTest(unittest.TestCase):
    def test_load_repo_manifests(self):
        caps = load_capabilities(Path("config/capabilities"))
        names = {c["name"] for c in caps}
        self.assertIn("agent:knowledge", names)
        self.assertIn("provider:omniroute", names)
        self.assertIn("tool:vercel_deploy", names)
        self.assertGreaterEqual(len(caps), 20)

    def test_render_contains_tables(self):
        caps = load_capabilities(Path("config/capabilities"))
        md = render_markdown(caps, manifest_dir=Path("config/capabilities"))
        self.assertIn("# KerrOS Capability Status", md)
        self.assertIn("| agent |", md)
        self.assertIn("provider:omniroute", md)
        self.assertIn("scripts/render_capabilities.py", md)

    def test_check_passes_when_current(self):
        # Ensure generated file exists and matches (modulo timestamp).
        self.assertEqual(main([]), 0)
        self.assertEqual(main(["--check"]), 0)

    def test_check_fails_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "CAPABILITIES.md"
            out.write_text("# stale\n", encoding="utf-8")
            self.assertEqual(main(["-o", str(out), "--check"]), 1)

    def test_normalize_strips_timestamp(self):
        a = "> Generated from `config/capabilities/*.yaml` by `scripts/render_capabilities.py` on **2026-01-01 00:00 UTC**.\n"
        b = "> Generated from `config/capabilities/*.yaml` by `scripts/render_capabilities.py` on **2099-12-31 23:59 UTC**.\n"
        self.assertEqual(_normalize_for_compare(a), _normalize_for_compare(b))


if __name__ == "__main__":
    unittest.main()
