import unittest
from manual_handoff import manual_handoff

DAY="2026-11-20"
def prepared(price=0):
    return {"status":"connection_found","accountVerifiedBeforeSearch":True,
            "connection":{"date":DAY,"departure":"18:22","displayedPriceCents":price}}

class HandoffTests(unittest.TestCase):
    def test_valid_readonly_handoff_never_authorizes(self):
        r=manual_handoff(DAY,prepared(),{"potentialDuplicate":False,"inventoryComplete":False})
        self.assertEqual(r["status"],"manual_review_required")
        self.assertFalse(r["bookingAuthorized"])
        self.assertFalse(r["purchaseExecuted"])
        self.assertFalse(r["allowLiveRequests"])
    def test_duplicate_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(),{"potentialDuplicate":True})["reason"],"possible_existing_reservation")
    def test_nonzero_price_blocks(self):
        self.assertEqual(manual_handoff(DAY,prepared(100))["reason"],"zero_euro_not_verified")
    def test_unverified_account_blocks(self):
        self.assertEqual(manual_handoff(DAY,{"status":"login_required"})["reason"],"account_unverified")
    def test_wrong_date_blocks(self):
        self.assertEqual(manual_handoff("2026-11-21",prepared())["reason"],"journey_mismatch")

if __name__=="__main__":
    unittest.main()
