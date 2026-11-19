#!/usr/bin/env python3
"""Offline regression tests for the actual checkout-review retry loop.

Reads the installed ticketshop_station_dry_run.py and compiles ONLY its
checkout-review 'for review_try in range(3)' AST node. No WESTbahn network,
browser, account, booking, checkout or write operations are executed.
"""
import ast
import os
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("ticketshop_station_dry_run.py")

def review_loop():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    matches = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "review_try"
        and isinstance(node.iter, ast.Call)
        and isinstance(node.iter.func, ast.Name)
        and node.iter.func.id == "range"
        and len(node.iter.args) == 1
        and isinstance(node.iter.args[0], ast.Constant)
        and node.iter.args[0].value == 3
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one checkout-review loop, found {len(matches)}")
    loop = matches[0]
    calls = [
        node for node in ast.walk(loop)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    allowed = {"evaluate", "wait_for_load_state", "wait_for_timeout", "get"}
    actual = {node.func.attr for node in calls}
    if actual - allowed:
        raise AssertionError(f"Unexpected calls in read-only retry: {actual - allowed}")
    return compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])),
                   str(SOURCE), "exec")

class FakePage:
    def __init__(self, failures):
        self.failures = failures
        self.attempts = 0
        self.waits = 0

    def evaluate(self, _javascript, _selected):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("Execution context was destroyed")
        return {"status": "read_only_reviewed",
                "finalPriceVerified": False,
                "purchaseExecuted": False}

    def wait_for_load_state(self, _state, timeout):
        assert timeout == 5000
        self.waits += 1

    def wait_for_timeout(self, _ms):
        pass

    def __getattr__(self, name):
        raise AssertionError("Unsafe browser operation: " + name)

class CheckoutReadOnlyRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiled = review_loop()

    def scenario(self, failures):
        page = FakePage(failures)
        result = {"checkoutReviewReadOnly": {"status": "not_attempted"}}
        namespace = {
            "page": page, "result": result,
            "seat_choice": {"code": "233A"},
            "range": range, "type": type
        }
        exec(self.compiled, namespace)
        return page, result["checkoutReviewReadOnly"]

    def test_no_navigation_race(self):
        page, result = self.scenario(0)
        self.assertEqual(page.attempts, 1)
        self.assertEqual(result["status"], "read_only_reviewed")

    def test_two_navigation_races_recover(self):
        page, result = self.scenario(2)
        self.assertEqual(page.attempts, 3)
        self.assertEqual(page.waits, 2)
        self.assertEqual(result["status"], "read_only_reviewed")

    def test_three_navigation_races_fail_closed(self):
        page, result = self.scenario(3)
        self.assertEqual(page.attempts, 3)
        self.assertEqual(result["status"], "navigation_unstable")
        self.assertIs(result["purchaseExecuted"], False)
        self.assertIs(result["finalPriceVerified"], False)

if __name__ == "__main__":
    unittest.main(verbosity=2)
