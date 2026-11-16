import unittest
from unittest.mock import Mock
from worker import safe_request_summary, classify_blocked_seat_requests

class RequestSequenceSafetyTests(unittest.TestCase):
    def test_request_summary_never_contains_sensitive_payload(self):
        req=Mock()
        req.url='https://westbahn.at/api/v1/secret-123?access_token=hidden'
        req.method='POST'
        req.resource_type='fetch'
        req.post_data='password=hidden'
        req.is_navigation_request.return_value=False
        item=safe_request_summary(req)
        item['requestIndex']=1
        self.assertEqual(item['requestIndex'],1)
        self.assertNotIn('hidden',str(item))
        self.assertNotIn('secret-123',str(item))
        self.assertNotIn('password=',str(item))

    def test_ordered_unknown_post_requests_never_authorize_live(self):
        reqs=[{'method':'POST','path':'/api/v1/:redacted','requestIndex':i} for i in range(1,6)]
        result=classify_blocked_seat_requests(reqs)
        self.assertEqual(result['categories']['unknown'],5)
        self.assertFalse(result['allowLiveRequests'])
        self.assertEqual([r['requestIndex'] for r in reqs],[1,2,3,4,5])

if __name__=='__main__':
    unittest.main()
