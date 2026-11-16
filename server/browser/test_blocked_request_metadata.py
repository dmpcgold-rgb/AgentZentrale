import unittest
from unittest.mock import Mock
from blocked_request_metadata import describe, abort_and_record

class BlockedMetadataTests(unittest.TestCase):
    def request(self,url,body=None,content_type="application/json"):
        r=Mock()
        r.url=url
        r.method="POST"
        r.post_data=body
        r.headers={"content-type":content_type,"authorization":"very-secret"}
        return r

    def test_json_key_paths_no_values(self):
        r=self.request("https://westbahn.at/api/booking/12345678/seat?date=2026-11-20&token=abc",
                       '{"passengers":[{"seat":{"number":"233A"}}],"token":"very-secret"}')
        result=describe(r)
        self.assertEqual(result["path"],"/api/booking/{id}/seat")
        self.assertIn("passengers" if False else "{field}[].seat.number",result["body_keys"])
        self.assertNotIn("233A",str(result))
        self.assertNotIn("very-secret",str(result))
        self.assertNotIn("abc",str(result))
        self.assertEqual(result["query_keys"],["date","{field}"])

    def test_external_host_is_redacted(self):
        r=self.request("https://example.org/customer/1234?secret=1234",'{"a":"b"}')
        result=describe(r)
        self.assertEqual(result["host"],"other-origin")
        self.assertEqual(result["path"],"/{redacted}")
        self.assertEqual(result["query_keys"],[])

    def test_untrusted_key_names_are_redacted(self):
        r=self.request("https://westbahn.at/api/seat",'{"user@example.com":"private","safe":{"field":"value"}}')
        result=describe(r)
        self.assertIn("{field}",result["body_keys"])
        self.assertNotIn("user@example.com",str(result))
        self.assertNotIn("private",str(result))

    def test_oversize_body_never_logged(self):
        r=self.request("https://westbahn.at/api/seat",'{"x":"'+"a"*70000+'"}')
        result=describe(r)
        self.assertEqual(result["body_keys"],["{non_json_or_oversize}"])
        self.assertNotIn("a"*100,str(result))

    def test_offline_guard_always_aborts(self):
        route=Mock()
        route.request=self.request("https://westbahn.at/api/seat",'{"seat":"233A"}')
        route.request.resource_type="fetch"
        blocked=[]
        abort_and_record(route,blocked)
        route.abort.assert_called_once_with()
        route.continue_.assert_not_called()
        route.fulfill.assert_not_called()
        self.assertEqual(len(blocked),1)
        self.assertNotIn("233A",str(blocked))

    def test_offline_guard_aborts_even_if_logging_fails(self):
        route=Mock()
        route.request.url="not-a-url"
        route.request.post_data=None
        route.request.headers={}
        route.request.resource_type="fetch"
        route.request.method="POST"
        blocked=[]
        abort_and_record(route,blocked,limit=0)
        route.abort.assert_called_once_with()
        route.continue_.assert_not_called()
        self.assertEqual(blocked,[])

if __name__=="__main__":
    unittest.main()
