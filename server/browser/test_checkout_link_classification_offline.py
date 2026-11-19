"""Verify checkout control classification against the real browser JS, offline.

The JS is extracted from the production checkout action inspection and run
with a minimal DOM stub under Node. No network, browser or booking API used.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")

def inspect_js():
    text=SOURCE.read_text(encoding="utf-8")
    match=re.search(r'action=page\.evaluate\(r"""(\(\) => \{.*?\})"""\)',text,re.S)
    if not match:
        raise AssertionError("Checkout control inspector not found")
    return match.group(1)

def run_case(controls,links,checkboxes=None):
    script=r"""
const inspector=JSON.parse(process.argv[1]);
const controls=JSON.parse(process.argv[2]);
const links=JSON.parse(process.argv[3]);
const checkboxes=JSON.parse(process.argv[4]);
const fake=(obj)=>({
  ...obj,
  getClientRects:()=>[{}],
  getAttribute:(key)=>key==="aria-label" ? (obj.ariaLabel || "") : null,
  innerText:obj.label||"",
  value:obj.label||"",
  href:obj.href||"",
  closest:()=>obj.termsLabel ? {innerText:obj.termsLabel} : null,
  parentElement:{innerText:obj.termsLabel||""},
});
const elements={
  "button,input[type=submit]":controls.map(fake),
  "a[href]":links.map(fake),
  'input[type="checkbox"][required]':checkboxes.filter(e=>e.required).map(fake),
  'input[type="checkbox"]':checkboxes.map(fake)
};
globalThis.document={querySelectorAll:(selector)=>elements[selector]||[]};
globalThis.getComputedStyle=()=>({visibility:"visible"});
globalThis.location={href:"https://westbahn.at/ticketshop/checkout",origin:"https://westbahn.at"};
const output=Function("return ("+inspector+")()")();
process.stdout.write(JSON.stringify(output));
"""
    if not shutil.which("node"):
        raise unittest.SkipTest("Node required for offline JS behavior test")
    proc=subprocess.run(
        ["node","-e",script,json.dumps(inspect_js()),json.dumps(controls),
         json.dumps(links),json.dumps(checkboxes or [])],
        capture_output=True,text=True,check=True,timeout=15)
    return json.loads(proc.stdout)

class CheckoutLinkClassificationTests(unittest.TestCase):
    def test_new_ticket_link_is_not_final_order(self):
        r=run_case([], [{"label":"Ticket kaufen","href":"https://westbahn.at/ticketshop/ticket-buchen/"}])
        self.assertEqual(r["candidateCount"],0)
        self.assertEqual(r["newTicketLinkCount"],1)
        self.assertEqual(r["unverifiedCheckoutLinkCount"],0)

    def test_unknown_booking_link_is_not_auto_approved(self):
        r=run_case([], [{"label":"Jetzt verbindlich buchen","href":"https://westbahn.at/ticketshop/unknown-commit"}])
        self.assertEqual(r["candidateCount"],0)
        self.assertEqual(r["unverifiedCheckoutLinkCount"],1)

    def test_explicit_final_button_is_detected(self):
        r=run_case([{"label":"Jetzt verbindlich bestellen","disabled":False}],[])
        self.assertEqual(r["candidateCount"],1)
        self.assertEqual(r["candidateIndex"],0)

    def test_unchecked_required_terms_still_block(self):
        r=run_case([{"label":"Jetzt verbindlich bestellen"}],[],
                   [{"checked":False,"disabled":False,"required":True}])
        self.assertEqual(r["uncheckedRequiredCount"],1)

    def test_zahlungspflichtig_bestellen_zero_eur_button(self):
        r=run_case([{"label":"Zahlungspflichtig bestellen","disabled":False}],[])
        self.assertEqual(r["candidateCount"],1)
        self.assertEqual(r["candidateIndex"],0)

    def test_zahlungspflichtig_bestellen_disabled_without_terms(self):
        r=run_case([{"label":"Zahlungspflichtig bestellen","disabled":True}],[],
                   [{"checked":False,"termsLabel":"Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn."}])
        self.assertEqual(r["candidateCount"],0)
        self.assertEqual(r["disabledCheckoutButtonCount"],1)
        self.assertEqual(r["uncheckedTermsCount"],1)

    def test_checked_terms_detected_but_not_automatically_changed(self):
        r=run_case([{"label":"Zahlungspflichtig bestellen","disabled":False}],[],
                   [{"checked":True,"termsLabel":"Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn."}])
        self.assertEqual(r["candidateCount"],1)
        self.assertEqual(r["termsCheckboxCount"],1)
        self.assertEqual(r["uncheckedTermsCount"],0)

if __name__=="__main__":
    unittest.main(verbosity=2)
