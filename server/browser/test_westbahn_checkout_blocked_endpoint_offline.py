#!/usr/bin/env python3
"""Offline audit for checkout endpoint diagnosis; no provider requests."""
import ast
import unittest
from pathlib import Path

SRC=Path(__file__).with_name("ticketshop_station_dry_run.py").read_text(encoding="utf-8")

class CheckoutBlockedEndpointEvidence(unittest.TestCase):
    def test_syntax(self):
        ast.parse(SRC)
    def test_payment_init_explicitly_guarded(self):
        self.assertIn('"create_order_not_armed_or_safety_gate_failed"',SRC)
        self.assertIn('"create_order_safety_gate_blocked_no_order_sent"',SRC)
        self.assertIn('"payment_method_read_limit_reached"',SRC)
        self.assertIn('"checkoutArmedAtBlock":bool(checkout_state["armed"])',SRC)
        self.assertIn('"checkoutRequestAlreadySent":bool(checkout_state["requestSent"])',SRC)
        self.assertIn('"checkoutBlockedRequests":network["checkoutBlockedRequests"]',SRC)
    def test_no_broad_payment_allowlist(self):
        self.assertIn('and u.path=="/ticketshop/payment-init"',SRC)
        self.assertIn('and checkout_state["armed"]',SRC)
        self.assertIn('and purchase_opt_in',SRC)
        self.assertIn('and approval_state["approvedRequestSent"]',SRC)
        self.assertIn('and CURRENT_STAGE=="one_time_zero_euro_checkout_action"',SRC)
        self.assertIn('=="application/json"',SRC)
        self.assertIn('and not checkout_marker.exists()',SRC)
    def test_no_request_payload_logging(self):
        segment=SRC.split('# Only endpoint metadata. Never log request bodies,',1)[1].split('network["checkoutBlockedRequests"].append',1)[0]
        self.assertNotIn('req.post_data',segment)
        self.assertNotIn('req.headers',segment)
        self.assertNotIn('req.url',segment)

if __name__=="__main__":
    unittest.main(verbosity=2)
