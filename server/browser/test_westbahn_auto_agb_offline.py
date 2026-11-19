"""Offline tests of the production WESTbahn AGB locator: no browser or purchase."""
import json
import re
import subprocess
import unittest
from pathlib import Path

SOURCE=Path(__file__).with_name("ticketshop_station_dry_run.py")

def locator_script():
    source=SOURCE.read_text(encoding="utf-8")
    matched=re.search(r'terms=page\.evaluate\(r"""(\(\) => \{.*?\})"""\)',source,re.S)
    if not matched:
        raise AssertionError("Production AGB locator not found")
    return matched.group(1)

def run(boxes):
    node=r"""
const fn=JSON.parse(process.argv[1]);
const boxes=JSON.parse(process.argv[2]).map(x=>({
  ...x,
  closest:()=>x.parentText?{innerText:x.parentText}:null,
  parentElement:{innerText:x.parentText||""},
  getAttribute:(key)=>key==="aria-label"?(x.ariaLabel||""):null
}));
global.document={querySelectorAll:(selector)=>
  selector==='input[type="checkbox"]'?boxes:
  selector==="label"?[]:[]};
console.log(JSON.stringify(Function("return ("+fn+")()")()));
"""
    p=subprocess.run(["node","-e",node,json.dumps(locator_script()),json.dumps(boxes)],
                     capture_output=True,text=True,check=True,timeout=12)
    return json.loads(p.stdout)

class AutoTermsLocator(unittest.TestCase):
    def test_unique_unchecked_terms(self):
        r=run([{"id":"privacy","parentText":"Newsletter","checked":False,"disabled":False},
               {"id":"terms","parentText":"Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn.","checked":False,"disabled":False}])
        self.assertEqual(r,{"matchingCount":1,"index":1,"checked":False,"disabled":False})
    def test_already_checked_terms(self):
        r=run([{"parentText":"Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn.","checked":True,"disabled":False}])
        self.assertEqual(r["matchingCount"],1)
        self.assertTrue(r["checked"])
    def test_ambiguous_terms_fail_closed(self):
        label="Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn."
        self.assertEqual(run([{"parentText":label},{"parentText":label}])["matchingCount"],2)
    def test_unrelated_checkbox_not_accepted(self):
        self.assertEqual(run([{"parentText":"Newsletter abonnieren"}])["matchingCount"],0)
    def test_gate_remains_conditional(self):
        source=SOURCE.read_text(encoding="utf-8")
        gate=source.index('if (checkout_verified and purchase_opt_in')
        auto=source.index('if os.environ.get("WESTBAHN_AUTO_ACCEPT_AGB")=="1":')
        action=source.index('action=page.evaluate(r"""() => {',auto)
        self.assertLess(gate,auto)
        self.assertLess(auto,action)
        self.assertIn('and not checkout_marker.exists()',source[gate:auto])
        self.assertIn('and approval_state["approvedRequestSent"]',source[gate:auto])
        self.assertIn('terms_box.check(timeout=5000)',source[auto:action])

if __name__=="__main__":
    unittest.main(verbosity=2)
