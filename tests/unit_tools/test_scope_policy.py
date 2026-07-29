"""Tests for declarative scope_gate policy YAML."""

import os
import tempfile
import unittest
import json
from pathlib import Path

from tools import scope_gate


class ScopePolicyTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_policy = os.environ.get("KERROS_SCOPE_POLICY")
        self._old_base = os.environ.get("KERROS_BASE")
        # Isolate scope.json writes under temp base.
        os.environ["KERROS_BASE"] = self._tmpdir.name
        cfg_dir = Path(self._tmpdir.name) / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (Path(self._tmpdir.name) / "config.json").write_text("{}", encoding="utf-8")
        # Must exist so kernel.config does not fall back to the repo scope.json.
        (cfg_dir / "scope.json").write_text(
            json.dumps(
                {
                    "authorized_targets": [],
                    "authorized_cidrs": [],
                    "require_explicit_authorization": True,
                    "deploy_armed_until": 0,
                }
            ),
            encoding="utf-8",
        )
        # Clear cached config so KERROS_BASE is re-read.
        try:
            import core.config as legacy
            legacy._cfg = None
        except Exception:
            pass
        scope_gate.reload_policy()

    def tearDown(self):
        if self._old_policy is None:
            os.environ.pop("KERROS_SCOPE_POLICY", None)
        else:
            os.environ["KERROS_SCOPE_POLICY"] = self._old_policy
        if self._old_base is None:
            os.environ.pop("KERROS_BASE", None)
        else:
            os.environ["KERROS_BASE"] = self._old_base
        try:
            import core.config as legacy
            legacy._cfg = None
        except Exception:
            pass
        scope_gate.reload_policy()
        self._tmpdir.cleanup()

    def _write_policy(self, text: str) -> Path:
        path = Path(self._tmpdir.name) / "scope_policy.yaml"
        path.write_text(text, encoding="utf-8")
        os.environ["KERROS_SCOPE_POLICY"] = str(path)
        scope_gate.reload_policy()
        return path

    def test_loads_repo_policy_by_default(self):
        # Without KERROS_SCOPE_POLICY, load from repo config after clearing env override.
        os.environ.pop("KERROS_SCOPE_POLICY", None)
        # Point base at repo so config/scope_policy.yaml resolves.
        repo = Path(__file__).resolve().parents[2]
        os.environ["KERROS_BASE"] = str(repo)
        policy = scope_gate.reload_policy()
        self.assertIn("nmap", policy["offensive_tools"])
        self.assertIn("vercel_deploy", policy["deploy_tools"])
        self.assertTrue(str(policy.get("source", "")).endswith("scope_policy.yaml"))

    def test_custom_policy_overrides_tool_classes(self):
        self._write_policy(
            """
version: 1
defaults:
  deploy_arm_minutes: 3
offensive_tools:
  - custom_scan
deploy_tools:
  - custom_deploy
messages:
  deploy_denied: "NOPE {tool}"
"""
        )
        self.assertEqual(scope_gate.tool_class("custom_scan"), "offensive")
        self.assertEqual(scope_gate.tool_class("custom_deploy"), "deploy")
        self.assertEqual(scope_gate.tool_class("nmap"), "passive")
        allowed, reason = scope_gate.check("custom_deploy", "")
        self.assertFalse(allowed)
        self.assertIn("NOPE custom_deploy", reason)
        self.assertEqual(scope_gate.arm_deploy(), 3)

    def test_policy_summary(self):
        summary = scope_gate.policy_summary()
        self.assertIn("offensive_tools", summary)
        self.assertIn("deploy_tools", summary)


if __name__ == "__main__":
    unittest.main()
