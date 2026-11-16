import unittest
from trip_plan import plan, seat_review_summary
DAY="2026-11-20"
def prepared(price=0):
    return {"accountVerifiedBeforeSearch":True,"status":"connection_found",
            "connection":{"date":DAY,"departure":"18:22","displayedPriceCents":price}}
class TripPlanTests(unittest.TestCase):
    def test_verified_trip_is_ready_for_review_not_booking(self):
        p=plan(DAY,prepared())
        self.assertEqual(p["status"],"ready_for_manual_seat_review")
        self.assertFalse(p["bookingAuthorized"])
        self.assertEqual(p["preferredSeats"][:2],["233A","233D"])
    def test_nonzero_fare_blocks(self):
        self.assertEqual(plan(DAY,prepared(100))["reason"],"zero_euro_not_verified")
    def test_unverified_login_blocks(self):
        self.assertEqual(plan(DAY,{})["reason"],"account_unverified")
    def test_unknown_seat_does_not_get_invented(self):
        r=seat_review_summary(plan(DAY,prepared()))
        self.assertIsNone(r["selectedSeat"])
        self.assertFalse(r["seatConfirmed"])
    def test_verified_seat_prepares_manual_checkout_only(self):
        observation={"verified":True,"seat":"233A","comfortClassVerified":True,
                     "wheelchair":False,"fourSeatGroup":False}
        r=seat_review_summary(plan(DAY,prepared()),observation)
        self.assertEqual(r["status"],"ready_for_manual_checkout_review")
        self.assertFalse(r["bookingAuthorized"])
        self.assertFalse(r["purchaseExecuted"])
    def test_unverified_layout_blocks(self):
        observation={"verified":True,"seat":"233A","comfortClassVerified":True}
        self.assertEqual(seat_review_summary(plan(DAY,prepared()),observation)["reason"],"seat_layout_unverified")
if __name__=="__main__":
    unittest.main()
