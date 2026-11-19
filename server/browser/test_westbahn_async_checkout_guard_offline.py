#!/usr/bin/env python3
"""Offline tests: one-shot asynchronous request window and public-only probe."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).parent
SHOP=(ROOT/"ticketshop_station_dry_run.py").read_text(encoding="utf-8")
PROBE=(ROOT/"westbahn_public_checkout_script_probe.py").read_text(encoding="utf-8")

class Safety(unittest.TestCase):
    def test_both_scripts_parse(self):
        ast.parse(SHOP)
        ast.parse(PROBE)
    def test_arm_is_held_through_async_wait(self):
        clicked=SHOP.index('CURRENT_STAGE="one_time_zero_euro_checkout_action"')
        wait=SHOP.index('page.wait_for_timeout(1800)',clicked)
        disarm=SHOP.index('checkout_state["armed"]=False',clicked)
        self.assertGreater(disarm,wait)
        self.assertLess(disarm,SHOP.index('checkout_action["requestSent"]=',clicked))
    def test_durable_one_request_only_guard_unchanged(self):
        self.assertIn('and not checkout_state["attempted"]',SHOP)
        self.assertIn('and not checkout_marker.exists()',SHOP)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',SHOP)
        self.assertIn('req.resource_type in ("fetch","xhr")',SHOP)
        self.assertIn('not req.is_navigation_request()',SHOP)
    def test_unknown_payment_init_still_blocked(self):
        self.assertIn('"payment_init_endpoint_not_verified"',SHOP)
        self.assertNotIn('and u.path=="/ticketshop/payment-init"\n',SHOP)
    def test_public_probe_is_get_only_and_unauthenticated(self):
        self.assertIn('method="GET"',PROBE)
        self.assertIn('HOSTS = {"westbahn.at", "www.westbahn.at"}',PROBE)
        self.assertIn('not parsed.password and not parsed.fragment',PROBE)
        self.assertIn('(parts.scheme,parts.netloc,parts.path,"","")',PROBE)
        self.assertIn('if safe_url(public_asset)',PROBE)
        self.assertIn('MAX_BYTES = 8 * 1024 * 1024',PROBE)
        self.assertNotIn('chromium',PROBE)
        self.assertNotIn('post_data',PROBE)

if __name__=="__main__":
    unittest.main(verbosity=2)
