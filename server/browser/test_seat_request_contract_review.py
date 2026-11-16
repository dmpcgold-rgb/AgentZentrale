import unittest
from seat_request_contract_review import review

class SeatRequestContractReviewTests(unittest.TestCase):
    def diagnostic(self, requests):
        return {"status": "seat_network_diagnostic", "blockedRequests": requests}

    def test_five_unknown_posts_remain_unverified(self):
        result = review(self.diagnostic([{"method":"POST","host":"other-origin","path":"/:redacted"}]*4+
                                        [{"method":"POST","host":"westbahn.at","path":"/api/v1/:redacted"}]))
        self.assertEqual(result["requestCount"], 5)
        self.assertEqual(result["riskCounts"]["mutation_possible"], 5)
        self.assertFalse(result["allowLiveRequests"])
        self.assertFalse(result["bookingAuthorized"])

    def test_provider_origin_separated_without_authorization(self):
        result = review(self.diagnostic([
            {"method":"POST","host":"other-origin","path":"/:redacted"},
            {"method":"POST","host":"other-origin","path":"/:redacted"},
            {"method":"POST","host":"other-origin","path":"/:redacted"},
            {"method":"POST","host":"other-origin","path":"/:redacted"},
            {"method":"POST","host":"westbahn.at","path":"/api/v1/:redacted"}]))
        self.assertEqual(result["originSummary"]["provider"]["requestIndices"], [5])
        self.assertEqual(result["originSummary"]["other_origin"]["count"], 4)
        self.assertFalse(result["originSummary"]["provider"]["liveRequestPermitted"])
        self.assertFalse(result["bookingAuthorized"])

    def test_post_requires_provider_contract(self):
        result = review(self.diagnostic([{"method":"POST","host":"westbahn.at",
                                          "path":"/api/v1/:redacted","hasBody":True}]))
        self.assertEqual(result["requests"][0]["evidenceNeeded"],
                         "provider_endpoint_contract_and_non_mutating_behavior")
        self.assertFalse(result["allowLiveRequests"])

    def test_external_get_requires_service_identification(self):
        result = review(self.diagnostic([{"method":"GET","host":"other-origin",
                                          "path":"/:redacted"}]))
        self.assertEqual(result["requests"][0]["evidenceNeeded"],
                         "identify_external_service_and_verify_data_handling")
        self.assertFalse(result["bookingAuthorized"])

    def test_get_does_not_grant_permission(self):
        result = review(self.diagnostic([{"method":"GET","host":"shop.westbahn.at","path":"/api/v1/availability"}]))
        self.assertEqual(result["requests"][0]["risk"], "read_candidate_only")
        self.assertFalse(result["allowLiveRequests"])

    def test_no_payload_or_secrets_copied(self):
        result = review(self.diagnostic([{"method":"POST","host":"westbahn.at","path":"/api/v1/:redacted",
                                          "postData":"secret","cookie":"secret","headers":{"Authorization":"secret"}}]))
        self.assertNotIn("secret", str(result))
        self.assertFalse(result["purchaseExecuted"])

    def test_missing_requests_fail_closed(self):
        result = review({"status":"seat_network_diagnostic"})
        self.assertEqual(result["status"], "review_blocked")
        self.assertFalse(result["allowLiveRequests"])

    def test_malformed_request_fail_closed(self):
        result = review(self.diagnostic(["bad"]))
        self.assertEqual(result["status"], "review_blocked")
        self.assertFalse(result["bookingAuthorized"])

if __name__ == "__main__":
    unittest.main()
