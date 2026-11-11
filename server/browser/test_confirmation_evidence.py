import unittest

from confirmation_evidence import reference_indicators, summarize_confirmation_candidates


class ConfirmationEvidenceTests(unittest.TestCase):
    def test_reference_indicators_hide_sensitive_codes(self):
        text='Reservierung Comfort Class Buchungsnummer: SECRET-123456 Ticketnummer: TK-123456'
        markers=reference_indicators(text)
        self.assertEqual(markers,{'bookingReference':True,'ticketReference':True})
        self.assertNotIn('SECRET',str(markers))
        self.assertNotIn('TK-123456',str(markers))

    def test_unrelated_purchase_dates_and_unlabeled_codes_are_not_refs(self):
        self.assertEqual(reference_indicators('Ticketcode PRIVATE123 Kaufdatum: 17.11.2026'),
                         {'bookingReference':False,'ticketReference':False})
        self.assertEqual(reference_indicators(None),
                         {'bookingReference':False,'ticketReference':False})

    def test_strong_candidate_requires_explicit_year_and_labeled_reference(self):
        card={'dateLabel':'DI 17 NOV','fullDate':'2026-11-17','seat':'191D',
              'bookingReference':True,'ticketReference':False}
        result=summarize_confirmation_candidates([card],'2026-11-17','191D')
        self.assertEqual(result['evidenceLevel'],'dated_reference_candidate')
        self.assertFalse(result['confirmationVerified'])
        self.assertFalse(result['bookingAuthorized'])
        self.assertFalse(result['inventoryComplete'])

    def test_yearless_ticket_has_no_automated_confirmation(self):
        card={'dateLabel':'DI 17 NOV','seat':'191D','bookingReference':True}
        result=summarize_confirmation_candidates([card],'2026-11-17','191D')
        self.assertEqual(result['evidenceLevel'],'visible_ticket_card')
        self.assertFalse(result['yearVerified'])
        self.assertFalse(result['confirmationVerified'])

    def test_wrong_seat_and_missing_ticket_are_never_confirmed(self):
        wrong={'dateLabel':'DI 17 NOV 2026','seat':'233A','bookingReference':True}
        for rows in ([wrong],[]):
            result=summarize_confirmation_candidates(rows,'2026-11-17','191D')
            self.assertNotEqual(result['evidenceLevel'],'dated_reference_candidate')
            self.assertFalse(result['confirmationVerified'])
            self.assertFalse(result['bookingAuthorized'])

    def test_mismatched_year_does_not_resolve(self):
        wrong={'dateLabel':'DI 17 NOV','fullDate':'2025-11-17','seat':'191D','bookingReference':True}
        result=summarize_confirmation_candidates([wrong],'2026-11-17','191D')
        self.assertEqual(result['evidenceLevel'],'not_proven')
        self.assertFalse(result['confirmationVerified'])


if __name__=='__main__':
    unittest.main()
