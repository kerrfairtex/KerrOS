"""Tests for Documentation-as-Code scope policy renderer."""

import tempfile
import unittest
from pathlib import Path

from scripts.render_scope_policy import (
    load_policy,
    main,
    render_markdown,
    _normalize_for_compare,
)


class RenderScopePolicyTest(unittest.TestCase):
    def test_load_repo_policy(self):
        policy = load_policy(Path("config/scope_policy.yaml"))
        self.assertIn("nmap", policy["offensive_tools"])
        self.assertIn("vercel_deploy", policy["deploy_tools"])
        self.assertEqual(policy["defaults"].get("deploy_arm_minutes"), 5)
        self.assertIn("deploy_denied", policy["messages"])

    def test_render_contains_tables(self):
        policy = load_policy(Path("config/scope_policy.yaml"))
        md = render_markdown(policy)
        self.assertIn("# KerrOS Scope Policy", md)
        self.assertIn("| offensive |", md)
        self.assertIn("| deploy |", md)
        self.assertIn("`nmap`", md)
        self.assertIn("`github_push`", md)
        self.assertIn("deploy_arm_minutes", md)
        self.assertIn("scripts/render_scope_policy.py", md)

    def test_check_passes_when_current(self):
        self.assertEqual(main([]), 0)
        self.assertEqual(main(["--check"]), 0)

    def test_check_fails_when_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "SCOPE_POLICY.md"
            out.write_text("# stale\n", encoding="utf-8")
            self.assertEqual(main(["-o", str(out), "--check"]), 1)

    def test_normalize_strips_timestamp(self):
        a = "> Generated from `config/scope_policy.yaml` by `scripts/render_scope_policy.py` on **2026-01-01 00:00 UTC**.\n"
        b = "> Generated from `config/scope_policy.yaml` by `scripts/render_scope_policy.py` on **2099-12-31 23:59 UTC**.\n"
        self.assertEqual(_normalize_for_compare(a), _normalize_for_compare(b))


if __name__ == "__main__":
    unittest.main()
