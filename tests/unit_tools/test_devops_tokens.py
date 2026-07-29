"""Least-privilege DevOps credential checks."""

from __future__ import annotations

import unittest

from tools.devops_tokens import (
    SERVICE_SPECS,
    TOOL_SERVICE,
    audit_all,
    check_service,
    check_tool,
    preflight,
    summary_table,
)


class DeployCredentialsTest(unittest.TestCase):
    def test_all_eight_services_defined(self):
        expected = {
            "github",
            "supabase",
            "vercel",
            "netlify",
            "railway",
            "cloudflare",
            "stripe",
        }
        self.assertEqual(set(SERVICE_SPECS), expected)
        self.assertEqual(len(TOOL_SERVICE), 8)

    def test_github_missing_fails(self):
        result = check_service("github", environ={})
        self.assertFalse(result.ok)
        self.assertIn("GITHUB_TOKEN", result.message)

    def test_github_present_ok(self):
        result = check_service("github", environ={"GITHUB_TOKEN": "ghp_example"})
        self.assertTrue(result.ok)
        self.assertEqual(result.env_used, "GITHUB_TOKEN")

    def test_netlify_accepts_legacy_alias(self):
        result = check_service(
            "netlify", environ={"NETLIFTY_API_KEY": "nlt_legacy"}
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.env_used, "NETLIFTY_API_KEY")

    def test_netlify_prefers_auth_token(self):
        result = check_service(
            "netlify",
            environ={
                "NETLIFY_AUTH_TOKEN": "nlt_new",
                "NETLIFTY_API_KEY": "nlt_legacy",
            },
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.env_used, "NETLIFY_AUTH_TOKEN")

    def test_stripe_rejects_live_secret(self):
        result = check_service(
            "stripe", environ={"STRIPE_API_KEY": "sk_live_should_fail"}
        )
        self.assertFalse(result.ok)
        self.assertIn("sk_live_", result.message)

    def test_stripe_rejects_live_restricted(self):
        result = check_service(
            "stripe", environ={"STRIPE_SECRET_KEY": "rk_live_nope"}
        )
        self.assertFalse(result.ok)

    def test_stripe_accepts_test_secret(self):
        result = check_service(
            "stripe", environ={"STRIPE_API_KEY": "sk_test_ok"}
        )
        self.assertTrue(result.ok)

    def test_stripe_accepts_test_restricted(self):
        result = check_service(
            "stripe", environ={"STRIPE_API_KEY": "rk_test_ok"}
        )
        self.assertTrue(result.ok)

    def test_stripe_rejects_unknown_prefix(self):
        result = check_service(
            "stripe", environ={"STRIPE_API_KEY": "pk_test_publishable"}
        )
        self.assertFalse(result.ok)

    def test_supabase_warns_on_service_role(self):
        result = check_service(
            "supabase",
            environ={
                "SUPABASE_ACCESS_TOKEN": "sbp_ok",
                "SUPABASE_SERVICE_ROLE_KEY": "service_role_secret",
            },
        )
        self.assertTrue(result.ok)
        self.assertTrue(any("SERVICE_ROLE" in w for w in result.warnings))

    def test_supabase_optional_without_token(self):
        result = check_service("supabase", environ={})
        self.assertTrue(result.ok)
        self.assertFalse(result.present)

    def test_preflight_blocks_and_allows(self):
        self.assertIn(
            "sk_live_",
            preflight("stripe_trigger", environ={"STRIPE_API_KEY": "sk_live_x"}) or "",
        )
        self.assertIsNone(
            preflight("stripe_trigger", environ={"STRIPE_API_KEY": "sk_test_ok"})
        )
        self.assertIn(
            "GITHUB_TOKEN",
            preflight("github_push", environ={}) or "",
        )

    def test_preflight_tool_mapping(self):
        result = check_tool("vercel_deploy", environ={})
        self.assertFalse(result.ok)
        self.assertEqual(result.service, "vercel")

    def test_audit_and_summary(self):
        checks = audit_all(environ={"GITHUB_TOKEN": "ghp_x", "VERCEL_TOKEN": "v"})
        self.assertEqual(len(checks), 7)
        text = summary_table(checks)
        self.assertIn("github", text)
        self.assertIn("stripe", text)


if __name__ == "__main__":
    unittest.main()
