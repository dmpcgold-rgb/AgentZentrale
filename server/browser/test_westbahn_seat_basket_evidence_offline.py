#!/usr/bin/env python3
"""Offline regression: exact basket seat evidence is sufficient without a separate seat-update call."""
import ast
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")
SRC=SOURCE.read_text(encoding="utf-8")
TREE=ast.parse(SRC)
MAIN=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="main")

def assignments():
    result={}
    for node in ast.walk(MAIN):
        if isinstance(node,ast.Assign) and len(node.targets)==1:
            n=node.targets[0]
            if isinstance(n,ast.Name) and n.id in ("matching_post_submit_basket_verified","seat_server_confirmed"):
                result[n.id]=node.value
    return result

class BasketSeatEvidence(unittest.TestCase):
    def test_exact_basket_required(self):
        node=assignments()["matching_post_submit_basket_verified"]
        s=ast.unparse(node)
        for field in ("itemCount","numericPriceIsZero","matchingDepartureDate","matchingDepartureTime","matchingTrain","seatTokensAnywhere","seatTokensInNamedFields"):
            self.assertIn(field,s)
        self.assertIn("selected_code",s)
    def test_no_unnecessary_second_seat_update_required(self):
        node=assignments()["seat_server_confirmed"]
        expr=compile(ast.Expression(node),str(SOURCE),"eval")
        self.assertTrue(eval(expr,{"seat_update_ok":False,"matching_post_submit_basket_verified":True}))
        self.assertFalse(eval(expr,{"seat_update_ok":False,"matching_post_submit_basket_verified":False}))
    def test_approval_still_requires_exact_matching_basket(self):
        self.assertIn("and matching_post_submit_basket_verified\n                    and not approval_marker.exists()",SRC)
        self.assertIn("and confirmed_form and zero_fare and seat_server_confirmed",SRC)
    def test_checkout_requires_verified_zero_total(self):
        self.assertIn('len(total_candidates)==1',SRC)
        self.assertIn('total_candidates[0].get("containsZero") is True',SRC)
        self.assertIn('total_candidates[0].get("containsNonzero") is False',SRC)
    def test_no_checkout_marker_reset(self):
        self.assertNotIn('checkout_marker.unlink(',SRC)

if __name__=="__main__":
    unittest.main(verbosity=2)
