import unittest
from unittest.mock import patch, MagicMock
import worker

DAY='2026-11-20'

class LivePreflightTests(unittest.TestCase):
    def page(self):
        p=MagicMock()
        p.context.pages=[]
        return p

    @patch.object(worker,'inspect_comfort_booking_control')
    def test_missing_ledger_blocks(self,control):
        control.return_value={'providerReservationState':'not_exposed_in_checked_web_views'}
        r=worker.inspect_live_seat_preflight(self.page(),DAY)
        self.assertEqual(r['reason'],'local_ledger_not_verified')
        self.assertFalse(r['bookingAuthorized'])

    @patch.object(worker,'inspect_comfort_booking_control')
    def test_existing_provider_reservation_blocks(self,control):
        control.return_value={'providerReservationState':'reservation_detected','localAttemptStatus':'NONE',
                              'bookingFieldState':'existing_reservation_blocked','bookingFieldClickable':False}
        r=worker.inspect_live_seat_preflight(self.page(),DAY)
        self.assertEqual(r['status'],'seat_preflight_inspected')
        self.assertEqual(r['reason'],'provider_reservation_exists')
        self.assertFalse(r['purchaseExecuted'])

    @patch.object(worker,'inspect_comfort_booking_control')
    def test_unverified_absence_never_authorizes(self,control):
        control.return_value={'providerReservationState':'not_exposed_in_checked_web_views','localAttemptStatus':'NONE',
                              'bookingFieldState':'enabled_zero_euro','bookingFieldClickable':True}
        p=self.page()
        r=worker.inspect_live_seat_preflight(p,DAY)
        self.assertFalse(r['bookingAuthorized'])
        self.assertFalse(r['purchaseExecuted'])
        self.assertEqual(len(p.context.pages),0)

if __name__=='__main__': unittest.main()
