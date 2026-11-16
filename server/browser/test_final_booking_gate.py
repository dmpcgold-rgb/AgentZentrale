import unittest
from final_booking_gate import final_booking_gate

DAY='2026-11-20'
CONN={'date':DAY,'departure':'18:22','arrival':'18:49','trainNumber':'1009',
      'displayedPriceCents':0,'priceSource':'comfort_control'}
CTRL={'bookingFieldState':'enabled_zero_euro','bookingFieldClickable':True}
PROVIDER={'found':False,'diagnosis':'not_exposed_in_checked_web_views'}
SEAT={'coach':'11','seat':'233A'}

def check(**kw):
    args=dict(day=DAY,connection=CONN,control=CTRL,provider=PROVIDER,
              local_status='NONE',selection=SEAT,provider_absence_verified=False)
    args.update(kw)
    return final_booking_gate(**args)

class FinalGateTests(unittest.TestCase):
    def test_unverified_absence_blocks(self):
        self.assertEqual(check()['reason'],'provider_absence_not_authoritative')
    def test_provider_existing_blocks(self):
        self.assertEqual(check(provider={'found':True,'diagnosis':'reservation_detected'})['reason'],'provider_reservation_exists')
    def test_pending_blocks(self):
        self.assertEqual(check(local_status='PENDING')['reason'],'local_duplicate_or_uncertain')
    def test_uncertain_blocks(self):
        self.assertEqual(check(local_status='UNCERTAIN')['reason'],'local_duplicate_or_uncertain')
    def test_paid_blocks(self):
        self.assertEqual(check(connection={**CONN,'displayedPriceCents':300},provider_absence_verified=True)['reason'],'connection_or_price_mismatch')
    def test_disabled_blocks(self):
        self.assertEqual(check(control={**CTRL,'bookingFieldClickable':False},provider_absence_verified=True)['reason'],'control_not_verified')
    def test_unverified_seat_blocks(self):
        self.assertEqual(check(selection={'coach':'11','seat':'193'},provider_absence_verified=True)['reason'],'seat_not_verified')
    def test_verified_preflight_never_authorizes_purchase(self):
        result=check(provider_absence_verified=True)
        self.assertEqual(result['status'],'preflight_verified')
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['purchaseExecuted'])

    def test_probably_unbooked_is_not_authoritative(self):
        result=check(provider={'found':False,'diagnosis':'probably_not_booked'})
        self.assertEqual(result['reason'],'provider_evidence_ambiguous')
        self.assertFalse(result['bookingAuthorized'])

    def test_unverified_provider_evidence_blocks_even_with_flag(self):
        result=check(provider={'found':None,'diagnosis':'not_exposed_in_checked_web_views'},
                     provider_absence_verified=True)
        self.assertEqual(result['reason'],'provider_evidence_ambiguous')
        self.assertFalse(result['purchaseExecuted'])

    def test_zero_euro_alone_does_not_authorize(self):
        result=check(selection=None)
        self.assertEqual(result['reason'],'provider_absence_not_authoritative')
        self.assertFalse(result['bookingAuthorized'])

    def test_confirmed_local_booking_blocks_even_with_absence_flag(self):
        result=check(local_status='CONFIRMED',provider_absence_verified=True)
        self.assertEqual(result['reason'],'local_duplicate_or_uncertain')
        self.assertFalse(result['purchaseExecuted'])

if __name__=='__main__': unittest.main()
