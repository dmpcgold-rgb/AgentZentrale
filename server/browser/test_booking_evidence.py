import unittest
from booking_evidence import assess_existing_ticket

class BookingEvidenceTests(unittest.TestCase):
    def test_finds_known_ticket_by_weekday_date_and_seat(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D'}]
        x=assess_existing_ticket(rows,'2026-11-17','191D')
        self.assertEqual(x['status'],'existing_ticket_visible')
        self.assertFalse(x['dateFullyVerified'])
        self.assertFalse(x['safeToBook'])
        self.assertTrue(x['matches'][0]['expectedSeat'])

    def test_wrong_seat_still_blocks_duplicate(self):
        x=assess_existing_ticket([{'dateLabel':'DI 17 NOV 2026','seat':'233A'}],'2026-11-17','191D')
        self.assertEqual(x['status'],'existing_ticket_visible')
        self.assertTrue(x['dateFullyVerified'])
        self.assertFalse(x['matches'][0]['expectedSeat'])
        self.assertFalse(x['safeToBook'])

    def test_unseen_never_allows_checkout(self):
        for rows in ([],[{'dateLabel':'DI 17 NOV','seat':'bad'}],
                     [{'dateLabel':'MO 16 NOV 2026','seat':'191D'}],
                     [{'dateLabel':'DI 17 NOV 2025','seat':'191D'}],None):
            x=assess_existing_ticket(rows,'2026-11-17','191D')
            self.assertFalse(x['safeToBook'])
            self.assertEqual(x['status'],'not_seen_in_incomplete_account')

    def test_reject_bad_inputs(self):
        self.assertEqual(assess_existing_ticket([],'2026-11-35')['status'],'invalid_date')
        self.assertEqual(assess_existing_ticket([],'2026-11-17','bad')['status'],'invalid_seat')

if __name__=='__main__':unittest.main()
