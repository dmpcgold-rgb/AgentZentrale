"""Isolated end-to-end WESTbahn checkout simulation.

Exercises actual production AGB selector, terminal button inspector, zero-EUR
journey guard and response-classification snippet with a synthetic DOM.
No browser profile, network, WESTbahn request, or real booking is accessed.
"""
import textwrap
import unittest
from pathlib import Path
from server.browser.test_westbahn_auto_agb_offline import run as terms_selector
from server.browser.test_checkout_link_classification_offline import run_case
from server.browser.test_westbahn_final_order_guard_offline import evaluate

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")
TERMS="Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn."

def final_response_state(responses,request_sent=True):
    source=SOURCE.read_text(encoding="utf-8")
    start=source.index('                            order_responses=network["checkoutOrderResponses"]')
    end=source.index('                            checkout_action["currentPath"]',start)
    snippet=textwrap.dedent(source[start:end])
    namespace={"network":{"checkoutOrderResponses":responses},
               "checkout_state":{"requestSent":request_sent},
               "checkout_action":{"status":"button_clicked","ticketConfirmed":False}}
    exec(compile(snippet,"<production-order-response-classification>","exec"),{},namespace)
    return namespace["checkout_action"]

def simulated_checkout(*,terms_count=1,price="Gesamtpreis 0,00 €",
                       date="20.11.2026",response_status=200,
                       response_missing=False):
    # These are simulated page state transitions, not remote Playwright calls.
    boxes=[{"parentText":TERMS,"checked":False,"disabled":False}
           for _ in range(terms_count)]
    matched=terms_selector(boxes)
    accepted=matched["matchingCount"]==1 and not matched["disabled"]
    if accepted:
        boxes[matched["index"]]["checked"]=True
    button=run_case(
        [{"label":"Zahlungspflichtig bestellen","disabled":not accepted}],
        [{"label":"Weitere Tickets kaufen",
          "href":"https://westbahn.at/ticketshop/ticket-buchen/"}],
        [{"checked":b["checked"],"required":True,"termsLabel":b["parentText"]}
         for b in boxes],
    )
    final=evaluate(total=price,date=date)
    allowed=(accepted and button["candidateCount"]==1
             and button["uncheckedRequiredCount"]==0
             and button["uncheckedTermsCount"]==0
             and final["verified"])
    # Simulated single request gate; a 200 response is NOT a confirmed ticket.
    response=[] if response_missing else [{"status":response_status,
                                           "ok":response_status<400}]
    classification=final_response_state(response,True) if allowed else None
    return {"termsAccepted":accepted,"finalButtonCount":button["candidateCount"],
            "zeroEuroTripVerified":final["verified"],"ordersSent":int(allowed),
            "response":classification}

class IsolatedCheckoutSimulation(unittest.TestCase):
    def test_normal_zero_eur_checkout_transport_accepted_ticket_unverified(self):
        result=simulated_checkout()
        self.assertTrue(result["termsAccepted"])
        self.assertEqual(result["finalButtonCount"],1)
        self.assertTrue(result["zeroEuroTripVerified"])
        self.assertEqual(result["ordersSent"],1)
        self.assertEqual(result["response"]["status"],
                         "final_order_http_accepted_ticket_unverified")
        self.assertFalse(result["response"]["ticketConfirmed"])
    def test_provider_rejects_order_no_retry(self):
        result=simulated_checkout(response_status=422)
        self.assertEqual(result["ordersSent"],1)
        self.assertEqual(result["response"]["status"],
                         "final_order_http_rejected_no_retry")
    def test_timeout_unknown_result_no_retry(self):
        result=simulated_checkout(response_missing=True)
        self.assertEqual(result["ordersSent"],1)
        self.assertEqual(result["response"]["status"],
                         "final_order_response_unknown_no_retry")
    def test_wrong_day_blocks_order(self):
        self.assertEqual(simulated_checkout(date="27.11.2026")["ordersSent"],0)
    def test_nonzero_price_blocks_order(self):
        self.assertEqual(simulated_checkout(price="Gesamtpreis 4,90 €")["ordersSent"],0)
    def test_missing_terms_blocks_order(self):
        self.assertEqual(simulated_checkout(terms_count=0)["ordersSent"],0)
    def test_ambiguous_terms_blocks_order(self):
        self.assertEqual(simulated_checkout(terms_count=2)["ordersSent"],0)
    def test_existing_previous_approval_markers_remain_guards(self):
        source=SOURCE.read_text(encoding="utf-8")
        self.assertIn('third_recovery_marker.exists()',source)
        self.assertIn('checkout_marker.exists()',source)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',source)

if __name__=="__main__":
    unittest.main(verbosity=2)
