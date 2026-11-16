import unittest
from seat_preflight_bridge import inspect_selected_seat

DAY='2026-11-20'
CONNECTION={'date':DAY,'departure':'18:22','arrival':'18:49','trainNumber':'1009','displayedPriceCents':0,'priceSource':'comfort_control'}
CONTROL={'bookingFieldState':'enabled_zero_euro','bookingFieldClickable':True}
PROVIDER={'found':False,'diagnosis':'not_exposed_in_checked_web_views'}
MODAL={'modalFound':True,'selected':{'coach':'11','seat':'233A'},'activeCoach':'11','comfortMap':True}
DETAIL={'verified':True,'date':DAY,'displayedPriceCents':0}

def evaluate(**overrides):
    args=dict(day=DAY,connection=CONNECTION,control=CONTROL,provider=PROVIDER,
              local_status='NONE',seat_modal=MODAL,detail_summary=DETAIL,
              provider_absence_verified=False)
    args.update(overrides)
    return inspect_selected_seat(**args)

class BridgeTests(unittest.TestCase):
    def test_live_like_state_still_blocks_purchase(self):
        r=evaluate()
        self.assertEqual(r['reason'],'provider_absence_not_authoritative')
        self.assertFalse(r['bookingAuthorized'])
    def test_existing_reservation_blocks(self):
        self.assertEqual(evaluate(provider={'found':True,'diagnosis':'reservation_detected'})['reason'],'provider_reservation_exists')
    def test_missing_modal_blocks(self):
        self.assertEqual(evaluate(seat_modal={**MODAL,'modalFound':False},provider_absence_verified=True)['reason'],'seat_not_verified')
    def test_wrong_active_coach_blocks(self):
        self.assertEqual(evaluate(seat_modal={**MODAL,'activeCoach':'8'},provider_absence_verified=True)['reason'],'seat_not_verified')
    def test_unverified_detail_blocks(self):
        self.assertEqual(evaluate(detail_summary={**DETAIL,'verified':False},provider_absence_verified=True)['reason'],'seat_not_verified')
    def test_unknown_seat_blocks(self):
        self.assertEqual(evaluate(seat_modal={**MODAL,'selected':{'coach':'11','seat':'999A'}},provider_absence_verified=True)['reason'],'seat_not_verified')
    def test_verified_preflight_is_not_purchase(self):
        r=evaluate(provider_absence_verified=True)
        self.assertEqual(r['status'],'preflight_verified')
        self.assertFalse(r['bookingAuthorized'])
        self.assertFalse(r['purchaseExecuted'])

if __name__=='__main__': unittest.main()
