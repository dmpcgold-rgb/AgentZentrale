#!/usr/bin/env python3
"""Verify seat dialog transition remains fail-closed; no browser or booking network."""
import ast
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")
SCRIPT=SOURCE.read_text(encoding="utf-8")

class SeatDialogSettlingTests(unittest.TestCase):
    def test_valid_python(self):
        ast.parse(SCRIPT)
    def test_wait_only_for_actual_modal_closure(self):
        self.assertIn('result["seatDialogConfirmation"]["clicked"]', SCRIPT)
        self.assertIn('page.wait_for_function(r"""() => {', SCRIPT)
        self.assertIn("filter(visible).length===0", SCRIPT)
        self.assertIn('"dialogClosedAfterConfirm"', SCRIPT)
    def test_no_forced_close_or_simulated_success(self):
        self.assertNotIn('confirm.click(force=True', SCRIPT)
        self.assertIn('seatShownInForm:dialogs.length===0 && matching.length===1', SCRIPT)
        self.assertIn('result["seatDialogConfirmation"]["clicked"] and', SCRIPT)
        self.assertIn('summary["seatShownInForm"]', SCRIPT)
    def test_one_shot_and_price_guards_retained(self):
        self.assertIn('approval_marker.exists()', SCRIPT)
        self.assertIn('checkout_marker.exists()', SCRIPT)
        self.assertIn('total_candidates[0].get("containsNonzero") is False', SCRIPT)

if __name__=="__main__":
    unittest.main(verbosity=2)
