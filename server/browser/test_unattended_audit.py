import unittest
from datetime import date
from unattended_audit import weekdays, safe_summary

class UnattendedAuditTests(unittest.TestCase):
    def test_weekends_skipped(self):
        self.assertEqual(weekdays(date(2026,11,13)),[
            "2026-11-13","2026-11-16","2026-11-17","2026-11-18","2026-11-19"])
    def test_missing_ticket_never_authorizes_purchase(self):
        dates=["2026-11-20"]
        result=safe_summary({"status":"inventory_batch_read","days":[
            {"date":dates[0],"status":"review_required","seats":[],
             "dateVerified":False,"privateToken":"SECRET"}]},dates)
        self.assertEqual(result["days"][0]["status"],"needs_review")
        self.assertFalse(result["bookingAuthorized"])
        self.assertFalse(result["purchaseExecuted"])
        self.assertNotIn("SECRET",str(result))
    def test_verified_existing_seat_is_reported(self):
        dates=["2026-11-18"]
        result=safe_summary({"status":"inventory_batch_read","days":[
            {"date":dates[0],"status":"detail_verified","seats":["233A"],
             "dateVerified":True}]},dates)
        self.assertEqual(result["days"][0]["seats"],["233A"])
    def test_invalid_and_duplicate_responses_fail_closed(self):
        dates=["2026-11-18","2026-11-19"]
        for payload in ({}, {"status":"inventory_batch_read","days":[]},
                        {"status":"inventory_batch_read","days":[
                         {"date":dates[0]},{"date":dates[0]}]}):
            self.assertEqual(safe_summary(payload,dates)["status"],"audit_blocked")
if __name__=="__main__":
    unittest.main()
