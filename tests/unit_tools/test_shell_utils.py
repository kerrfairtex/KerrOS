"""Tests for safe subprocess helpers."""

import unittest
import subprocess

from tools.shell_utils import (
    ShellCommandError,
    contains_shell_metacharacters,
    run_argv,
    sanitize_target,
    sanitize_token,
    split_command,
)


class ShellUtilsTest(unittest.TestCase):
    def test_split_simple_command(self):
        self.assertEqual(split_command("echo hello"), ["echo", "hello"])

    def test_rejects_pipe(self):
        with self.assertRaises(ShellCommandError):
            split_command("echo hello | rm -rf /")

    def test_rejects_semicolon(self):
        self.assertTrue(contains_shell_metacharacters("echo; whoami"))

    def test_rejects_ampersand(self):
        self.assertTrue(contains_shell_metacharacters("echo && whoami"))

    def test_rejects_dollar_substitution(self):
        self.assertTrue(contains_shell_metacharacters("echo $(whoami)"))
        self.assertTrue(contains_shell_metacharacters("echo ${HOME}"))

    def test_rejects_redirect(self):
        self.assertTrue(contains_shell_metacharacters("echo > /etc/passwd"))
        self.assertTrue(contains_shell_metacharacters("echo < /etc/passwd"))

    def test_rejects_newlines(self):
        self.assertTrue(contains_shell_metacharacters("echo\nwhoami"))

    def test_allows_safe_flags(self):
        argv = split_command("ping -c 1 127.0.0.1")
        self.assertEqual(argv, ["ping", "-c", "1", "127.0.0.1"])

    def test_sanitize_target_valid(self):
        self.assertEqual(sanitize_target("example.com"), "example.com")
        self.assertEqual(sanitize_target("192.168.1.1"), "192.168.1.1")

    def test_sanitize_target_rejects_injection(self):
        with self.assertRaises(ShellCommandError):
            sanitize_target("example.com; rm -rf /")

    def test_sanitize_target_rejects_path_traversal(self):
        with self.assertRaises(ShellCommandError):
            sanitize_target("../../../etc/passwd")

    def test_sanitize_token_valid(self):
        self.assertEqual(sanitize_token("my-branch/v1.2"), "my-branch/v1.2")

    def test_sanitize_token_rejects_injection(self):
        with self.assertRaises(ShellCommandError):
            sanitize_token("token; rm -rf /")

    def test_run_argv_echo(self):
        out = run_argv(["echo", "safe"], timeout=5)
        self.assertIn("safe", out)

    def test_run_argv_missing_binary(self):
        out = run_argv(["nonexistent_binary_xyz"], timeout=5)
        self.assertIn("not found", out)

    def test_run_argv_timeout(self):
        out = run_argv(["sleep", "10"], timeout=0.1)
        self.assertIn("Timeout", out)


if __name__ == "__main__":
    unittest.main()
