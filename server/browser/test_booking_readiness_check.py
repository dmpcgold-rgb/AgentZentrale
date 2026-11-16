import unittest
from unittest.mock import patch
import worker

class ReadinessTests(unittest.TestCase):
    @patch.object(worker,'inspect_comfort_booking_control')
    @patch.object(worker,'inspect_paginated_reservation_evidence')
    def test_possible_duplicate_stops_before_control(self,inventory,control):
        inventory.return_value={'potentialDuplicate':True,'inventoryComplete':False}
        r=worker.inspect_booking_readiness(type('P',(),{'context':object()})(),'2026-11-20')
        self.assertEqual(r['reason'],'possible_existing_reservation')
        self.assertFalse(r['bookingAuthorized'])
        control.assert_not_called()

    @patch.object(worker,'inspect_comfort_booking_control')
    @patch.object(worker,'inspect_paginated_reservation_evidence')
    def test_zero_euro_never_authorizes_without_absence_proof(self,inventory,control):
        inventory.return_value={'potentialDuplicate':False,'inventoryComplete':False,'pagesVerified':2}
        control.return_value={'bookingFieldState':'enabled_zero_euro','bookingFieldClickable':True}
        r=worker.inspect_booking_readiness(type('P',(),{'context':object()})(),'2026-11-20')
        self.assertEqual(r['reason'],'provider_absence_not_authoritative')
        self.assertFalse(r['readyToPurchase'])
        self.assertFalse(r['purchaseExecuted'])

    @patch.object(worker,'inspect_comfort_booking_control')
    @patch.object(worker,'inspect_paginated_reservation_evidence')
    def test_disabled_control_stays_blocked(self,inventory,control):
        inventory.return_value={'potentialDuplicate':False,'inventoryComplete':False}
        control.return_value={'bookingFieldState':'disabled','bookingFieldClickable':False}
        r=worker.inspect_booking_readiness(type('P',(),{'context':object()})(),'2026-11-20')
        self.assertEqual(r['reason'],'control_not_verified')
        self.assertFalse(r['bookingAuthorized'])


    @patch.object(worker,'inspect_comfort_booking_control')
    @patch.object(worker,'inspect_paginated_reservation_evidence')
    def test_no_visible_booking_is_probable_not_authoritative(self,inventory,control):
        inventory.return_value={'potentialDuplicate':False,'inventoryComplete':False,
                                'pagesVerified':2,'pagesFailed':0,'candidateStatus':'review_required'}
        control.return_value={'bookingFieldState':'enabled_zero_euro',
                              'providerReservationState':'not_exposed_in_checked_web_views',
                              'localAttemptStatus':'NONE'}
        result=worker.inspect_booking_readiness(type('P',(),{'context':object()})(),'2026-11-20')
        self.assertEqual(result['reservationLikelihood'],'probably_not_booked')
        self.assertTrue(result['seatSelectionReviewAllowed'])
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    @patch.object(worker,'inspect_comfort_booking_control')
    @patch.object(worker,'inspect_paginated_reservation_evidence')
    def test_failed_page_never_counts_as_probably_unbooked(self,inventory,control):
        inventory.return_value={'potentialDuplicate':False,'pagesVerified':2,'pagesFailed':1,
                                'candidateStatus':'review_required'}
        result=worker.inspect_booking_readiness(type('P',(),{'context':object()})(),'2026-11-20')
        self.assertEqual(result['reservationLikelihood'],'unknown')
        self.assertFalse(result['bookingAuthorized'])
        control.assert_not_called()

if __name__=='__main__': unittest.main()
