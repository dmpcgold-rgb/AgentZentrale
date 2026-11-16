import unittest
from seat_request_contract_review import review

class ContractMetadataTests(unittest.TestCase):
    def test_sanitized_fields_survive_review(self):
        record={"method":"POST","host":"westbahn.at","path":"/api/{id}",
                "resourceType":"fetch","query_keys":["date"],"body_keys":["seat.number"],
                "content_type":"application/json","body_size_bytes":42,
                "timestamp_utc":"2026-11-16T13:00:00+00:00","step":"seat_selection"}
        result=review({"status":"seat_network_diagnostic","blockedRequests":[record]})
        row=result["requests"][0]
        for key in ("query_keys","body_keys","content_type","body_size_bytes","timestamp_utc","step"):
            self.assertEqual(row[key],record[key])
        self.assertEqual(row["risk"],"mutation_possible")
        self.assertFalse(result["allowLiveRequests"])
        self.assertFalse(result["purchaseExecuted"])

    def test_missing_fields_never_invented(self):
        result=review({"status":"seat_network_diagnostic","blockedRequests":[{"method":"POST","host":"other-origin","path":"/{redacted}"}]})
        self.assertIsNone(result["requests"][0]["body_keys"])
        self.assertFalse(result["allowLiveRequests"])

if __name__=="__main__":
    unittest.main()
