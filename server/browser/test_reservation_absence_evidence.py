"""Read-only regression tests: missing tickets are never proof of absence."""
import unittest
from unittest.mock import patch
import worker


class ReservationAbsenceEvidenceTests(unittest.TestCase):
    def check(self, reports, status='review_required', duplicate=False):
        inventory={'reports':reports,'matchingVisibleCards':[]}
        summary={'days':[{'date':'2026-11-20','status':status,'potentialDuplicate':duplicate,'seats':[]}]}
        with patch.object(worker,'account_inventory',return_value=inventory), patch.object(
                worker,'summarize_inventory_batch',return_value=summary):
            return worker.inspect_paginated_reservation_evidence(object(),'2026-11-20')

    def test_two_pages_never_prove_absence(self):
        result=self.check([{'status':'account_verified','page':1},
                           {'status':'account_verified','page':2}])
        self.assertFalse(result['inventoryComplete'])
        self.assertEqual(result['absenceEvidence']['status'],'not_proven')
        self.assertEqual(result['absenceEvidence']['reason'],'provider_total_not_verified')
        self.assertFalse(result['bookingAuthorized'])

    def test_failed_page_is_reported(self):
        result=self.check([{'status':'account_verified','page':1},
                           {'status':'http_error','page':2}])
        self.assertEqual(result['absenceEvidence']['reason'],'page_failures')
        self.assertEqual(result['absenceEvidence']['failedPages'],1)

    def test_unverified_pagination_is_reported(self):
        result=self.check([{'status':'account_verified','page':1,'paginationLinks':[2,3]},
                           {'status':'account_verified','page':2}])
        self.assertEqual(result['absenceEvidence']['reason'],'pagination_unverified')
        self.assertEqual(result['absenceEvidence']['unverifiedPaginationLinks'],1)

    def test_positive_evidence_never_becomes_absence(self):
        result=self.check([{'status':'account_verified','page':1}],duplicate=True)
        self.assertEqual(result['absenceEvidence']['status'],'positive_booking_evidence')
        self.assertTrue(result['potentialDuplicate'])
        self.assertFalse(result['purchaseExecuted'])


if __name__=='__main__':
    unittest.main()
