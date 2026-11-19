"""Offline simulation of the owner-attested recovery5 policy.

No WESTbahn networking, Playwright, marker writes or checkout calls.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest

SRC=Path(__file__).with_name("ticketshop_station_dry_run.py").read_text()
START=SRC.index('        prior_approval=root/"approval_attempt_20261120.flag"')
END=SRC.index('        with sync_playwright() as p:',START)
BODY=SRC[START:END]
scope={}
exec(compile("def check(root,os,json):"+chr(10)+BODY+
             "        return locals()"+chr(10),
             "<offline-owner-policy>","exec"),scope)
check=scope["check"]

class Recovery5Safety(unittest.TestCase):
    def evaluate(self,flags,*,past=True,fifth=False,checkout=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            if past:
                (root/"approval_attempt_20261120_recovery4.flag").write_text("past")
            if fifth:
                (root/"approval_attempt_20261120_recovery5.flag").write_text("attempted")
            if checkout:
                (root/"checkout_attempt_20261120.flag").write_text("attempted")
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                value=check(root,types.SimpleNamespace(environ=flags),json)
            return value,output.getvalue()

    def flags(self):
        return {"WESTBAHN_OWNER_AUTHORIZED_RECOVERY5_20261120":"1",
                "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120":"1",
                "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120":"1"}

    def test_exact_three_flags_and_prior_fourth_marker_required(self):
        result,_=self.evaluate(self.flags())
        self.assertTrue(result["fifth_recovery_requested"])
        for flag in self.flags():
            env=self.flags()
            env.pop(flag)
            blocked,_=self.evaluate(env)
            self.assertIsNone(blocked)
        self.assertFalse(self.evaluate(self.flags(),past=False)[0]["fifth_recovery_requested"])
    def test_fifth_attempt_marker_is_not_reusable(self):
        result,out=self.evaluate(self.flags(),fifth=True)
        self.assertIsNone(result)
        self.assertIn("fifth_recovery_already_attempted",out)
    def test_terminal_checkout_marker_always_blocks(self):
        result,out=self.evaluate(self.flags(),checkout=True)
        self.assertIsNone(result)
        self.assertIn("checkout_already_attempted",out)
    def test_default_without_flags_still_blocks_old_recovery(self):
        result,_=self.evaluate({})
        self.assertIsNone(result)
    def test_approval_marker_selects_new_unique_path(self):
        self.assertIn('fifth_recovery_marker\n                    if fifth_recovery_requested',SRC)
        self.assertIn('and not approval_marker.exists()',SRC)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',SRC)
        self.assertNotIn('fifth_recovery_marker.unlink(',SRC)

if __name__=="__main__":
    unittest.main()
