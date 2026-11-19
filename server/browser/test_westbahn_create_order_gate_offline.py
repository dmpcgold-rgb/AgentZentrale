"""Evaluate the production createOrder allow-gate offline; never send network requests."""
import ast
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC=Path(__file__).with_name("ticketshop_station_dry_run.py").read_text(encoding="utf-8")
START=SRC.index('                    final_post=(\n')
END=SRC.index('                    if final_post:', START)
GATE=textwrap.dedent(SRC[START:END])

class FakeMarker:
    def __init__(self,exists): self.value=exists
    def exists(self): return self.value

def decision(*,path="/ticketshop/payment-init",method="POST",
             type="application/json",host="westbahn.at",arm=True,
             opted=True,approved=True,attempted=False,marker=False,
             stage="one_time_zero_euro_checkout_action",query="",
             resource="fetch",navigation=False):
    req=SimpleNamespace(method=method,resource_type=resource,
        is_navigation_request=lambda: navigation,
        headers={"content-type":type})
    u=SimpleNamespace(scheme="https",hostname=host,port=None,
        path=path,query=query,fragment="")
    checkout_state={"armed":arm,"attempted":attempted}
    approval_state={"approvedRequestSent":approved}
    local={"req":req,"u":u,"checkout_state":checkout_state,
           "approval_state":approval_state,"checkout_marker":FakeMarker(marker),
           "purchase_opt_in":opted,"CURRENT_STAGE":stage}
    exec(compile(GATE,"<production-create-order-gate>","exec"),{},local)
    return local["final_post"]

class CreateOrderGate(unittest.TestCase):
    def test_parses(self): ast.parse(SRC)
    def test_known_json_order_inside_verified_window(self):
        self.assertTrue(decision())
    def test_existing_marker_blocks(self):
        self.assertFalse(decision(marker=True))
    def test_one_shot_attempt_prevents_repeat(self):
        self.assertFalse(decision(attempted=True))
    def test_not_armed_or_not_opted(self):
        self.assertFalse(decision(arm=False))
        self.assertFalse(decision(opted=False))
        self.assertFalse(decision(approved=False))
        self.assertFalse(decision(stage="startup"))
    def test_unknown_mutations_disallowed(self):
        for path in ("/ticketshop/basket/approve",
                     "/ticketshop/payment/confirm",
                     "/ticketshop/payment/payment-methods",
                     "/ticketshop/payment-init/another",
                     "/ticketshop/order/complete"):
            with self.subTest(path=path):
                self.assertFalse(decision(path=path))
    def test_headers_query_origin_and_method(self):
        self.assertFalse(decision(type="text/plain"))
        self.assertFalse(decision(query="token=123"))
        self.assertFalse(decision(host="other.example"))
        self.assertFalse(decision(method="GET"))
        self.assertFalse(decision(resource="document"))
        self.assertFalse(decision(navigation=True))

if __name__=="__main__":
    unittest.main()
