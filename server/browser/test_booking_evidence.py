import unittest
from booking_evidence import assess_existing_ticket, extract_explicit_trip_date

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

    def test_explicit_trip_date_resolves_yearless_label(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D','fullDate':'2026-11-17'}]
        evidence=assess_existing_ticket(rows,'2026-11-17','191D')
        self.assertEqual(evidence['status'],'existing_ticket_visible')
        self.assertTrue(evidence['dateFullyVerified'])
        self.assertFalse(evidence['safeToBook'])

    def test_wrong_explicit_year_never_matches(self):
        rows=[{'dateLabel':'DI 17 NOV','seat':'191D','fullDate':'2025-11-17'}]
        evidence=assess_existing_ticket(rows,'2026-11-17','191D')
        self.assertEqual(evidence['status'],'not_seen_in_incomplete_account')
        self.assertFalse(evidence['safeToBook'])

    def test_explicit_trip_date_is_scoped_and_unique(self):
        self.assertEqual(extract_explicit_trip_date('Abfahrt: 17.11.2026 18:22'), '2026-11-17')
        self.assertEqual(extract_explicit_trip_date('Fahrtdatum 17.11.2026'), '2026-11-17')
        self.assertIsNone(extract_explicit_trip_date('Kaufdatum: 17.11.2026'))
        self.assertIsNone(extract_explicit_trip_date('DI 17 NOV'))
        self.assertIsNone(extract_explicit_trip_date('Abfahrt 17.11.2026 Reisedatum 18.11.2026'))
        self.assertIsNone(extract_explicit_trip_date('Abfahrt 31.02.2026'))

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
