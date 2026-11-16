import tempfile
import unittest
from pathlib import Path
from booking_ledger import AttemptLedger
from booking_reconciliation import reconcile_days

JOURNEY='westbahn|Wien Meidling|Wiener Neustadt Hbf|18:22|Comfort2+'


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'ledger.sqlite')
        db=AttemptLedger(self.path)
        db.close()
        self.summary={'status':'audit_completed','days':[
            {'date':'2026-11-20','status':'needs_review','seats':[]},
            {'date':'2026-11-19','status':'existing_verified','seats':['208D']}],
            'bookingAuthorized':False,'purchaseExecuted':False}

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_provider_ticket_does_not_authorize_booking(self):
        result=reconcile_days(self.summary,self.path,JOURNEY)
        self.assertEqual(result['days'][0]['bookingBlockReason'],'provider_absence_unverified')
        self.assertFalse(result['safeToBook'])

    def test_provider_verified_ticket_is_blocked(self):
        result=reconcile_days(self.summary,self.path,JOURNEY)
        self.assertEqual(result['days'][1]['bookingBlockReason'],'provider_ticket_verified')

    def test_local_uncertain_overrides_missing_provider_card(self):
        db=AttemptLedger(self.path)
        claim=db.claim(JOURNEY,'2026-11-20')
        db.transition(claim['attempt_id'],'UNCERTAIN')
        db.close()
        result=reconcile_days(self.summary,self.path,JOURNEY)
        self.assertEqual(result['days'][0]['bookingBlockReason'],'local_uncertain')

    def test_missing_ledger_fails_closed(self):
        result=reconcile_days(self.summary,None,JOURNEY)
        self.assertEqual(result['status'],'audit_blocked')
        self.assertFalse(result['bookingAuthorized'])

    def test_corrupt_ledger_fails_closed(self):
        Path(self.path).write_text('not a sqlite database')
        result=reconcile_days(self.summary,self.path,JOURNEY)
        self.assertEqual(result['status'],'audit_blocked')

    def test_unexpected_provider_status_fails_closed(self):
        self.summary['days'][0]['status']='unbooked_authorized'
        result=reconcile_days(self.summary,self.path,JOURNEY)
        self.assertEqual(result['status'],'audit_blocked')


if __name__=='__main__':
    unittest.main()
