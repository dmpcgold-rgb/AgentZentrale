import tempfile
import unittest
from pathlib import Path
from booking_ledger import AttemptLedger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.a = AttemptLedger(self.path)
        self.b = AttemptLedger(self.path)
        self.journey = 'account:westbahn|Wien Meidling|Wiener Neustadt Hbf|18:22|Comfort2+'
        self.day = '2026-11-20'

    def tearDown(self):
        self.a.close()
        self.b.close()
        self.tmp.cleanup()

    def test_second_process_blocked(self):
        first = self.a.claim(self.journey, self.day)
        self.assertTrue(first['claimed'])
        second = self.b.claim(self.journey, self.day)
        self.assertFalse(second['claimed'])
        self.assertEqual(second['reason'], 'already_pending')

    def test_idempotency_key_cannot_book_twice(self):
        self.assertTrue(self.a.claim(self.journey, self.day, 'request-1')['claimed'])
        self.assertEqual(self.b.claim(self.journey, self.day, 'request-1')['reason'], 'idempotent_replay')

    def test_key_cannot_be_reused_for_another_day(self):
        self.a.claim(self.journey, self.day, 'request-1')
        self.assertEqual(self.b.claim(self.journey, '2026-11-23', 'request-1')['reason'],
                         'key_reused_for_different_journey')

    def test_uncertain_remains_blocked(self):
        claim = self.a.claim(self.journey, self.day)
        self.assertTrue(self.a.transition(claim['attempt_id'], 'UNCERTAIN'))
        self.assertEqual(self.b.claim(self.journey, self.day)['reason'], 'already_uncertain')

    def test_confirmation_requires_provider_proof(self):
        claim = self.a.claim(self.journey, self.day)
        self.assertFalse(self.a.transition(claim['attempt_id'], 'CONFIRMED'))
        self.assertTrue(self.a.transition(claim['attempt_id'], 'CONFIRMED', confirmed_by_provider=True))
        self.assertEqual(self.b.claim(self.journey, self.day)['reason'], 'already_confirmed')

    def test_failed_can_retry_but_old_key_cannot(self):
        claim = self.a.claim(self.journey, self.day, 'request-1')
        self.assertTrue(self.a.transition(claim['attempt_id'], 'FAILED'))
        self.assertFalse(self.b.claim(self.journey, self.day, 'request-1')['claimed'])
        self.assertTrue(self.b.claim(self.journey, self.day, 'request-2')['claimed'])

    def test_persists_across_reopen(self):
        self.a.claim(self.journey, self.day)
        self.a.close()
        self.a = AttemptLedger(self.path)
        self.assertEqual(self.a.status(self.journey, self.day), 'PENDING')

    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            self.a.claim(self.journey, '20.11.2026')


if __name__ == '__main__':
    unittest.main()
