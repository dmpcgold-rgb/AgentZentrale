"""Offline regression checks for final WESTbahn checkout revalidation.

Executes the exact JavaScript checkout finalDom inspector from production
with mocked DOM. Never contacts WESTbahn or mutates orders.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name("ticketshop_station_dry_run.py")

def inspector():
    source = SOURCE.read_text(encoding="utf-8")
    match = re.search(r'final_dom=page\.evaluate\(r"""(\(seat\) => \{.*?\})""",seat_choice',source,re.S)
    if match is None:
        raise AssertionError("Production final-order DOM review was not found")
    return match.group(1)

def evaluate(*,date="20.11.2026",total="Gesamtpreis 0,00 €",
             seat="191D",path="/ticketshop/checkout",
             train="1009",origin="Wien Meidling",destination="Wiener Neustadt"):
    js=r"""
const fn=JSON.parse(process.argv[1]);
const data=JSON.parse(process.argv[2]);
const text=[data.date,data.seat,"18:22",data.train,
            data.origin,data.destination,data.total].join(" ");
const element={
  innerText:data.total,
  children:[],
  getClientRects:()=>[{}]
};
global.document={
  querySelector:(selector)=>selector==="main"?{
    innerText:text,querySelectorAll:()=>[element]
  }:null
};
global.getComputedStyle=()=>({visibility:"visible"});
global.location={pathname:data.path};
process.stdout.write(JSON.stringify(Function("return ("+fn+")")()(data.seat)));
"""
    data={"date":date,"total":total,"seat":seat,"path":path,
          "train":train,"origin":origin,"destination":destination}
    p=subprocess.run(["node","-e",js,json.dumps(inspector()),json.dumps(data)],
                     check=True,text=True,capture_output=True,timeout=15)
    return json.loads(p.stdout)

class FinalOrderGuardTests(unittest.TestCase):
    def test_exact_zero_euro_trip(self):
        self.assertTrue(evaluate()["verified"])
    def test_wrong_date_blocked(self):
        self.assertFalse(evaluate(date="27.11.2026")["verified"])
    def test_nonzero_total_blocked(self):
        self.assertFalse(evaluate(total="Gesamtpreis 1,00 €")["verified"])
    def test_wrong_train_blocked(self):
        self.assertFalse(evaluate(train="1010")["verified"])
    def test_other_checkout_path_blocked(self):
        self.assertFalse(evaluate(path="/ticketshop/ticket-buchen/")["verified"])
    def test_empty_cart_blocked(self):
        self.assertFalse(evaluate(total="Warenkorb ist leer")["verified"])
    def test_order_request_is_one_shot(self):
        s=SOURCE.read_text(encoding="utf-8")
        self.assertIn('and not checkout_marker.exists()',s)
        self.assertIn('not checkout_state["attempted"]',s)
        self.assertIn('os.O_CREAT|os.O_EXCL|os.O_WRONLY',s)
        self.assertIn('button_clicked_no_verified_order_request',s)
        self.assertIn('final_order_request_sent_verification_pending',s)

if __name__=="__main__":
    unittest.main(verbosity=2)
