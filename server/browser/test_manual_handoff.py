import unittest
from manual_handoff import manual_handoff

DAY="2026-11-20"
def prepared(price=0):
    return {"status":"connection_found","accountVerifiedBeforeSearch":True,
            "connection":{"date":DAY,"departure":"18:22","origin":"Wien Meidling",
                          "destination":"Wiener Neustadt Hbf","class":"2+",
                          "displayedPriceCents":price}}

class HandoffTests(unittest.TestCase):
    def test_valid_readonly_handoff_never_authorizes(self):
        r=manual_handoff(DAY,prepared(),{"potentialDuplicate":False,"inventoryComplete":False,"pagesVerified":2,"pagesFailed":0},local_status="NONE")
        self.assertEqual(r["status"],"manual_review_required")
        self.assertFalse(r["bookingAuthorized"])
        self.assertFalse(r["purchaseExecuted"])
        self.assertFalse(r["allowLiveRequests"])
    def test_duplicate_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(),{"potentialDuplicate":True},local_status="NONE")["reason"],"possible_existing_reservation")
    def test_nonzero_price_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(100))["reason"],"zero_euro_not_verified")
    def test_unverified_account_blocks(self):
        self.assertEqual(manual_handoff(DAY,{"status":"login_required"})["reason"],"account_unverified")
    def test_wrong_date_blocks(self):
        self.assertEqual(manual_handoff("2026-11-21",prepared())["reason"],"journey_mismatch")

    def test_wrong_origin_blocks(self):
        p=prepared()
        p["connection"]["origin"]="Wien Westbahnhof"
        self.assertEqual(manual_handoff(DAY,p)["reason"],"journey_mismatch")
    def test_wrong_destination_blocks(self):
        p=prepared()
        p["connection"]["destination"]="Salzburg Hbf"
        self.assertEqual(manual_handoff(DAY,p)["reason"],"journey_mismatch")
    def test_wrong_comfort_class_blocks(self):
        p=prepared()
        p["connection"]["class"]="2"
        self.assertEqual(manual_handoff(DAY,p)["reason"],"journey_mismatch")
    def test_missing_route_metadata_blocks(self):
        p=prepared()
        del p["connection"]["origin"]
        self.assertEqual(manual_handoff(DAY,p)["reason"],"journey_mismatch")

    def test_local_pending_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(),{"potentialDuplicate":False},local_status="PENDING")["reason"],"local_duplicate_or_uncertain")
    def test_missing_ledger_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(),{"potentialDuplicate":False})["reason"],"local_ledger_not_verified")
    def test_failed_inventory_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(),{"pagesFailed":1},local_status="NONE")["reason"],"provider_inventory_inspection_failed")

if __name__=="__main__":
    unittest.main()
