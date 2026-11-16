import unittest
from unittest.mock import Mock
from worker import safe_request_summary

class SafeRequestMetadataTests(unittest.TestCase):
    def test_post_does_not_expose_body_or_query(self):
        req = Mock()
        req.url = "https://westbahn.at/api/v1/private-token?secret=123"
        req.method = "POST"
        req.resource_type = "fetch"
        req.post_data = '{"token":"supersecret"}'
        req.is_navigation_request.return_value = False
        result = safe_request_summary(req)
        self.assertEqual(result["path"], "/api/v1/:redacted")
        self.assertTrue(result["hasBody"])
        self.assertFalse(result["isNavigationRequest"])
        self.assertTrue(result["hasQuery"])
        self.assertNotIn("supersecret", str(result))
        self.assertNotIn("private-token", str(result))
        self.assertNotIn("123", str(result))

    def test_get_has_no_body(self):
        req = Mock()
        req.url = "https://westbahn.at/api/v1/availability"
        req.method = "GET"
        req.resource_type = "fetch"
        req.post_data = None
        req.is_navigation_request.return_value = False
        result = safe_request_summary(req)
        self.assertFalse(result["hasBody"])
        self.assertEqual(result["path"], "/api/v1/availability")

    def test_untrusted_host_is_redacted(self):
        req = Mock()
        req.url = "https://example.org/private/account?token=secret"
        req.method = "POST"
        req.resource_type = "fetch"
        req.post_data = "secret"
        req.is_navigation_request.return_value = False
        result = safe_request_summary(req)
        self.assertEqual(result["host"], "other-origin")
        self.assertEqual(result["path"], "/:redacted")
        self.assertNotIn("example.org", str(result))

if __name__ == "__main__":
    unittest.main()
