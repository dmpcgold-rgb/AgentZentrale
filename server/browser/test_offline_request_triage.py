import unittest
from offline_request_triage import triage

class OfflineRequestTriageTests(unittest.TestCase):
    def diagnostic(self, requests):
        return {"status": "seat_network_diagnostic", "blockedRequests": requests}

    def test_unknown_post_stays_blocked(self):
        r = triage(self.diagnostic([{"method": "POST", "host": "westbahn.at", "path": "/api/v1/:redacted"}]))
        self.assertEqual(r["counts"]["unknown"], 1)
        self.assertFalse(r["allowLiveRequests"])
        self.assertFalse(r["bookingAuthorized"])

    def test_get_read_candidate_is_not_authorized(self):
        r = triage(self.diagnostic([{"method": "GET", "host": "westbahn.at", "path": "/api/v1/availability"}]))
        self.assertEqual(r["counts"]["read_candidate"], 1)
        self.assertFalse(r["allowLiveRequests"])

    def test_post_to_booking_is_write_risk(self):
        r = triage(self.diagnostic([{"method": "POST", "host": "westbahn.at", "path": "/api/v1/booking"}]))
        self.assertEqual(r["counts"]["write_risk"], 1)
        self.assertFalse(r["bookingAuthorized"])

    def test_other_origin_get_cannot_be_read_candidate(self):
        r = triage(self.diagnostic([{"method": "GET", "host": "other-origin", "path": "/api/v1/availability"}]))
        self.assertEqual(r["counts"]["read_candidate"], 0)
        self.assertEqual(r["counts"]["unknown"], 1)
        self.assertFalse(r["allowLiveRequests"])

    def test_invalid_input_blocks(self):
        self.assertFalse(triage({})["allowLiveRequests"])

    def test_all_five_unknown_remain_blocked(self):
        r = triage(self.diagnostic([{"method": "POST", "host": "other-origin", "path": "/:redacted"}] * 4 +
                                   [{"method": "POST", "host": "westbahn.at", "path": "/api/v1/:redacted"}]))
        self.assertEqual(r["counts"], {"read_candidate": 0, "write_risk": 0, "unknown": 5})
        self.assertTrue(r["requiresProviderContractReview"])

if __name__ == "__main__":
    unittest.main()
