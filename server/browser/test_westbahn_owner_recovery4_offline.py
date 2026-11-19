"""Offline checks for a single owner-authorized 20 November recovery attempt.

Does not contact WESTbahn, create a marker or invoke Playwright.
"""
import ast
import re
import unittest
from pathlib import Path

SRC=Path(__file__).with_name("ticketshop_station_dry_run.py")

def policy():
    source=SRC.read_text(encoding="utf-8")
    beginning=source.index('        prior_approval=root/"approval_attempt_20261120.flag"')
    end=source.index('        with sync_playwright() as p:',beginning)
    segment=source[beginning:end]
    # Extract executable gate inside a local function, letting tests inspect
    # AST without ever running a checkout or changing persisted data.
    compiled="def evaluate_policy(root, os, json, sync_playwright):\n"+segment+"        return locals()\n"
    return ast.parse(compiled),segment

class OwnerAttestedFinalRecovery(unittest.TestCase):
    def test_python_syntax_compiles(self):
        ast.parse(SRC.read_text(encoding="utf-8"))
        policy()
    def test_only_explicit_owner_attestation_enables_fifth_attempt(self):
        _,segment=policy()
        self.assertIn('WESTBAHN_OWNER_AUTHORIZED_FINAL_RECOVERY4_20261120',segment)
        self.assertIn('WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120',segment)
        self.assertIn('WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120',segment)
        self.assertIn('and third_recovery_marker.exists()',segment)
        self.assertIn('and not fourth_recovery_requested',segment)
    def test_fifth_attempt_has_independent_durable_marker(self):
        src=SRC.read_text(encoding="utf-8")
        self.assertIn('approval_attempt_20261120_recovery4.flag',src)
        self.assertIn('if fourth_recovery_requested\n                    else third_recovery_marker',src)
        self.assertIn('or fourth_recovery_marker.exists()',src)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',src)
    def test_checkout_marker_blocks_even_authorized_recovery(self):
        _,segment=policy()
        self.assertRegex(segment,r'if \(\(root/"checkout_attempt_20261120.flag"\)\.exists\(\)')
    def test_no_marker_cleanup_logic(self):
        src=SRC.read_text(encoding="utf-8")
        self.assertNotIn('fourth_recovery_marker.unlink(',src)
        self.assertNotIn('third_recovery_marker.unlink(',src)

if __name__=="__main__":
    unittest.main(verbosity=2)
