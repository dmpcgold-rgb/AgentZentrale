import unittest
from unittest.mock import patch
import worker

DAY='2026-11-20'
class PaginationEvidenceTests(unittest.TestCase):
    @patch.object(worker,'summarize_inventory_batch')
    @patch.object(worker,'account_inventory')
    def test_existing_candidate_is_detected(self,inventory,summary):
        inventory.return_value={'matchingVisibleCards':[],'reports':[{'status':'account_verified'}]}
        summary.return_value={'days':[{'date':DAY,'status':'possible_existing','potentialDuplicate':True,'seats':['233A']}]}
        r=worker.inspect_paginated_reservation_evidence(object(),DAY)
        self.assertTrue(r['potentialDuplicate'])
        self.assertFalse(r['bookingAuthorized'])
        self.assertEqual(r['candidateSeats'],['233A'])

    @patch.object(worker,'summarize_inventory_batch')
    @patch.object(worker,'account_inventory')
    def test_no_visible_candidate_never_authorizes(self,inventory,summary):
        inventory.return_value={'matchingVisibleCards':[],'reports':[{'status':'account_verified'},{'status':'timeout'}]}
        summary.return_value={'days':[{'date':DAY,'status':'needs_review','potentialDuplicate':False,'seats':[]}]}
        r=worker.inspect_paginated_reservation_evidence(object(),DAY)
        self.assertEqual(r['reason'],'absence_not_authoritative')
        self.assertFalse(r['bookingAuthorized'])
        self.assertFalse(r['purchaseExecuted'])
        self.assertEqual(r['pagesFailed'],1)

    @patch.object(worker,'account_inventory',side_effect=RuntimeError('private data'))
    def test_inventory_failure_fails_closed(self,inventory):
        r=worker.inspect_paginated_reservation_evidence(object(),DAY)
        self.assertEqual(r['reason'],'inventory_inspection_failed')
        self.assertFalse(r['bookingAuthorized'])
        self.assertNotIn('private data',str(r))

if __name__=='__main__': unittest.main()
