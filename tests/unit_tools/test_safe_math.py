"""Tests for AST-based safe math evaluator."""

import unittest

from tools.safe_math import SafeMathError, safe_eval


class SafeMathTest(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(safe_eval("1 + 2 * 3"), 7)
        self.assertEqual(safe_eval("(1 + 2) * 3"), 9)
        self.assertEqual(safe_eval("10 // 3"), 3)
        self.assertEqual(safe_eval("10 % 3"), 1)

    def test_caret_power(self):
        self.assertEqual(safe_eval("2^8"), 256)
        self.assertEqual(safe_eval("2**10"), 1024)

    def test_unary_and_constants(self):
        self.assertEqual(safe_eval("-5 + 2"), -3)
        self.assertAlmostEqual(safe_eval("pi"), 3.141592653589793, places=5)

    def test_allowed_functions(self):
        self.assertEqual(safe_eval("sqrt(16)"), 4.0)
        self.assertEqual(safe_eval("abs(-7)"), 7)
        self.assertEqual(safe_eval("floor(3.9)"), 3)

    def test_rejects_attribute_access(self):
        with self.assertRaises(SafeMathError):
            safe_eval("().__class__")

    def test_rejects_unknown_names(self):
        with self.assertRaises(SafeMathError):
            safe_eval("os.system('id')")

    def test_rejects_disallowed_calls(self):
        with self.assertRaises(SafeMathError):
            safe_eval("__import__('os')")
        with self.assertRaises(SafeMathError):
            safe_eval("open('/etc/passwd')")

    def test_rejects_empty_and_long(self):
        with self.assertRaises(SafeMathError):
            safe_eval("")
        with self.assertRaises(SafeMathError):
            safe_eval("1+" * 300 + "1")

    def test_router_calc_wrapper(self):
        from kernel.router import _calc

        self.assertEqual(_calc("2^3"), "= 8")
        self.assertEqual(_calc("sqrt(9)"), "= 3.0")
        self.assertEqual(_calc("__import__('os')"), "[Invalid expression]")
        self.assertEqual(_calc("1/0"), "[Invalid expression]")


if __name__ == "__main__":
    unittest.main()
