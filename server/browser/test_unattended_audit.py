import unittest
from datetime import date
from unattended_audit import weekdays, safe_summary, inspect_unbooked_days
from unittest.mock import patch, Mock

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
    def test_inspection_never_authorizes_purchase(self):
        summary={"status":"audit_completed","days":[
            {"date":"2026-11-20","status":"needs_review","seats":[]}]}
        worker_result={"accountVerifiedBeforeSearch":True,
                       "bookingAuthorized":False,
                       "connection":{"displayedPriceCents":0}}
        with patch("unattended_audit.subprocess.run",
                   return_value=Mock(returncode=0,stdout=__import__("json").dumps(worker_result))) as runner:
            result=inspect_unbooked_days(summary)
        self.assertEqual(result["days"][0]["fareInspection"],"zero_euro_observed")
        self.assertFalse(result["bookingAuthorized"])
        self.assertFalse(result["purchaseExecuted"])
        self.assertIn("comfort-inspect",runner.call_args.args[0])
    def test_inspection_rejects_boolean_price(self):
        summary={"status":"audit_completed","days":[
            {"date":"2026-11-20","status":"needs_review","seats":[]}]}
        worker_result={"accountVerifiedBeforeSearch":True,"bookingAuthorized":False,
                       "connection":{"displayedPriceCents":False}}
        with patch("unattended_audit.subprocess.run",
                   return_value=Mock(returncode=0,stdout=__import__("json").dumps(worker_result))):
            result=inspect_unbooked_days(summary)
        self.assertEqual(result["days"][0]["fareInspection"],"unverified")
    def test_invalid_and_duplicate_responses_fail_closed(self):
        dates=["2026-11-18","2026-11-19"]
        for payload in ({}, {"status":"inventory_batch_read","days":[]},
                        {"status":"inventory_batch_read","days":[
                         {"date":dates[0]},{"date":dates[0]}]}):
            self.assertEqual(safe_summary(payload,dates)["status"],"audit_blocked")
if __name__=="__main__":
    unittest.main()
