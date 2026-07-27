"""Tests for safe subprocess helpers."""

import unittest

from tools.shell_utils import (
    ShellCommandError,
    contains_shell_metacharacters,
    run_argv,
    sanitize_target,
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

    def test_sanitize_target_valid(self):
        self.assertEqual(sanitize_target("example.com"), "example.com")
        self.assertEqual(sanitize_target("192.168.1.1"), "192.168.1.1")

    def test_sanitize_target_rejects_injection(self):
        with self.assertRaises(ShellCommandError):
            sanitize_target("example.com; rm -rf /")

    def test_run_argv_echo(self):
        out = run_argv(["echo", "safe"], timeout=5)
        self.assertIn("safe", out)


if __name__ == "__main__":
    unittest.main()
