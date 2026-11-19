#!/usr/bin/env python3
"""Offline tests for WESTbahn's fourth, one-time approval marker.

No network, browser, credentials, account or order requests are used.
Loads the actual script AST so the tested gate is the shipped gate.
"""
import ast
import os
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
MAIN=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="main")

def one(node):
    return compile(ast.Expression(body=node),str(SOURCE),"eval")

def locate():
    ass={}
    guard=None
    selector=None
    for node in ast.walk(MAIN):
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            n=node.targets[0].id
            if n in ("third_recovery_marker","final_recovery_marker","recovery_marker","prior_approval","third_recovery_requested","recovery_requested","final_recovery_requested"):
                ass[n]=node.value
            if n=="approval_marker":
                selector=node.value
        if isinstance(node,ast.If) and "previous_approval_attempt_requires_inventory_check" in ast.get_source_segment(SOURCE.read_text(encoding="utf-8"),node)[:1200]:
            guard=node.test
    assert len(ass)==7 and guard is not None and selector is not None
    return ass,guard,selector

class Recovery3GateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assignments,cls.guard,cls.selector=locate()

    def evaluate(self,flags,markers,checkout=False):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for marker in markers:
                (root/marker).touch()
            if checkout:
                (root/"checkout_attempt_20261120.flag").touch()
            env={"root":root,"os":os}
            old={k:os.environ.get(k) for k in flags}
            names=("WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120",
                   "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120",
                   "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120")
            old.update({k:os.environ.get(k) for k in names})
            try:
                for k in names:
                    os.environ.pop(k,None)
                os.environ.update(flags)
                for n in ("prior_approval","recovery_marker","final_recovery_marker","third_recovery_marker",
                          "third_recovery_requested","recovery_requested","final_recovery_requested"):
                    env[n]=eval(one(self.assignments[n]),env)
                blocked=eval(one(self.guard),env)
                marker=eval(one(self.selector),env).name
                return blocked,marker
            finally:
                for k,v in old.items():
                    if v is None:
                        os.environ.pop(k,None)
                    else:
                        os.environ[k]=v

    def test_existing_three_require_explicit_opt_in(self):
        markers=["approval_attempt_20261120.flag",
                 "approval_attempt_20261120_recovery1.flag",
                 "approval_attempt_20261120_recovery2.flag"]
        blocked,_=self.evaluate({},markers)
        self.assertTrue(blocked)
        flags={"WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120":"1",
               "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120":"1",
               "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120":"1"}
        blocked,target=self.evaluate(flags,markers)
        self.assertFalse(blocked)
        self.assertEqual(target,"approval_attempt_20261120_recovery3.flag")

    def test_partial_permission_is_not_enough(self):
        markers=["approval_attempt_20261120.flag",
                 "approval_attempt_20261120_recovery1.flag",
                 "approval_attempt_20261120_recovery2.flag"]
        for key in ("WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120",
                    "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120",
                    "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120"):
            flags={"WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120":"1",
                   "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120":"1",
                   "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120":"1"}
            flags.pop(key)
            self.assertTrue(self.evaluate(flags,markers)[0])

    def test_fourth_marker_blocks_retries(self):
        markers=["approval_attempt_20261120.flag",
                 "approval_attempt_20261120_recovery1.flag",
                 "approval_attempt_20261120_recovery2.flag",
                 "approval_attempt_20261120_recovery3.flag"]
        flags={"WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120":"1",
               "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120":"1",
               "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120":"1"}
        self.assertTrue(self.evaluate(flags,markers)[0])

    def test_checkout_attempt_blocks_even_with_permission(self):
        markers=["approval_attempt_20261120.flag",
                 "approval_attempt_20261120_recovery1.flag",
                 "approval_attempt_20261120_recovery2.flag"]
        flags={"WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120":"1",
               "WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120":"1",
               "WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120":"1"}
        self.assertTrue(self.evaluate(flags,markers,checkout=True)[0])

if __name__=="__main__":
    unittest.main(verbosity=2)
