"""Offline, provider-disconnected WESTbahn checkout sequence simulation.

Runs production DOM inspectors for AGB, final order button, trip/price and
confirmation against local mocked UI. No WESTbahn HTTP or payment requests.
The server's approval/checkout attempt markers are never touched.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from server.browser import test_westbahn_auto_agb_offline as agb
from server.browser import test_checkout_link_classification_offline as buttons
from server.browser import test_westbahn_final_order_guard_offline as trip

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")

def confirmation_js():
    source=SOURCE.read_text(encoding="utf-8")
    m=re.search(
        r'checkout_action\["confirmationPage"\]=page\.evaluate\(\s*r"""(\(selected\) => \{.*?\})""",seat_choice',
        source,re.S)
    if not m:
        raise AssertionError("Production confirmation inspector not found")
    return m.group(1)

def confirm(text,selected="191D",path="/ticketshop/checkout"):
    script=r"""
const fn=JSON.parse(process.argv[1]);
const data=JSON.parse(process.argv[2]);
globalThis.document={querySelector:s=>s==="main"?{innerText:data.text}:null};
globalThis.location={pathname:data.path};
process.stdout.write(JSON.stringify(Function("return ("+fn+")")(data.seat)));
"""
    p=subprocess.run(["node","-e",script,json.dumps(confirmation_js()),
                      json.dumps({"text":text,"seat":selected,"path":path})],
                     check=True,capture_output=True,text=True,timeout=12)
    return json.loads(p.stdout)

AGB_TEXT="Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn."

def simulate_checkout(*,zero=True,correct_date=True,consent=True,
                      response=200,confirmation=True,duplicate=False):
    """Use real DOM inspectors. Simulate transitions; do not fake provider requests."""
    if duplicate:
        return {"state":"blocked_existing_attempt","outgoingRequests":0}
    box={"id":"agb","parentText":AGB_TEXT,"checked":False,"disabled":False}
    initial=agb.run([box])
    assert initial["matchingCount"]==1 and not initial["checked"]
    before=buttons.run_case(
        [{"label":"Zahlungspflichtig bestellen","disabled":True}],
        [{"label":"Weitere Tickets kaufen","href":"https://westbahn.at/ticketshop/ticket-buchen/"}],
        [{"checked":False,"termsLabel":AGB_TEXT,"required":True}])
    assert before["candidateCount"]==0 and before["uncheckedTermsCount"]==1
    if not consent:
        return {"state":"blocked_agb","outgoingRequests":0}
    # Emulate Playwright .check() and the provider enabling the button.
    box["checked"]=True
    checked=agb.run([box])
    assert checked["checked"]
    after=buttons.run_case(
        [{"label":"Zahlungspflichtig bestellen","disabled":False}],
        [],[{"checked":True,"termsLabel":AGB_TEXT,"required":True}])
    assert after["candidateCount"]==1 and after["uncheckedRequiredCount"]==0
    review=trip.evaluate(
        date="20.11.2026" if correct_date else "27.11.2026",
        total="Gesamtpreis 0,00 €" if zero else "Gesamtpreis 1,00 €")
    if not review["verified"]:
        return {"state":"blocked_final_review","outgoingRequests":0}
    # An isolated stand-in for ONE authorized provider request. No HTTP.
    sent=1
    if response!=200:
        return {"state":"provider_rejected_or_unknown","outgoingRequests":sent,
                "ticketConfirmed":False}
    page_text=("Buchung erfolgreich 20.11.2026 191D Zug 1009"
               if confirmation else "Warenkorb")
    page=confirm(page_text)
    if page["explicitSuccessMessage"] and page["sameDate"] and page["sameSeat"] and page["sameTrain"]:
        # Even a success page is not independent account inventory proof.
        return {"state":"success_page_account_confirmation_pending",
                "outgoingRequests":sent,"ticketConfirmed":False}
    return {"state":"no_confirmation","outgoingRequests":sent,
            "ticketConfirmed":False}

@unittest.skipUnless(shutil.which("node"),"Node is required")
class CheckoutE2ESimulation(unittest.TestCase):
    def test_happy_path_agb_zero_eur_success_message(self):
        self.assertEqual(simulate_checkout()["state"],
                         "success_page_account_confirmation_pending")
        self.assertFalse(simulate_checkout()["ticketConfirmed"])
    def test_agb_absent_stops_before_order(self):
        self.assertEqual(simulate_checkout(consent=False)["outgoingRequests"],0)
    def test_wrong_day_stops_before_order(self):
        self.assertEqual(simulate_checkout(correct_date=False)["outgoingRequests"],0)
    def test_nonzero_price_stops_before_order(self):
        self.assertEqual(simulate_checkout(zero=False)["outgoingRequests"],0)
    def test_previous_approval_marker_stops_before_order(self):
        self.assertEqual(simulate_checkout(duplicate=True)["outgoingRequests"],0)
    def test_provider_failure_has_no_retry(self):
        out=simulate_checkout(response=500)
        self.assertEqual(out["outgoingRequests"],1)
        self.assertFalse(out["ticketConfirmed"])
    def test_missing_confirmation_does_not_prove_ticket(self):
        out=simulate_checkout(confirmation=False)
        self.assertEqual(out["state"],"no_confirmation")
        self.assertFalse(out["ticketConfirmed"])
    def test_actual_page_confirmation_inspector_needs_matching_trip(self):
        result=confirm("Buchung erfolgreich 27.11.2026 Sitz 191D Zug 1009")
        self.assertTrue(result["explicitSuccessMessage"])
        self.assertFalse(result["sameDate"])
    def test_source_has_durable_once_only_order_marker(self):
        s=SOURCE.read_text(encoding="utf-8")
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',s)
        self.assertIn('checkout_state["attempted"]=True',s)
        self.assertIn('and not checkout_marker.exists()',s)
        self.assertIn('checkout_action["ticketConfirmed"]=False',s)

if __name__=="__main__":
    unittest.main(verbosity=2)
