"""Regression tests for WESTbahn ticket-code evidence. Run: python -m unittest discover -s server/browser/tests -p 'test_ticket_code_evidence.py'"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from confirmation_evidence import reference_indicators, summarize_confirmation_candidates
from inventory_batch import summarize_inventory_batch

class TicketCodeEvidenceTests(unittest.TestCase):
    def test_real_card_labels_are_recognized_without_exposing_values(self):
        text = ("Reservierung Comfort Class MI 18 NOV Abfahrt 18:22 "
                "Wien Meidling Ankunft 18:49 Wiener Neustadt "
                "Sitzplatz 233A Ticketnummer 199-2797-4304 Ticketcode BWF-VMB")
        evidence = reference_indicators(text)
        self.assertTrue(evidence['ticketReference'])
        self.assertTrue(evidence['ticketCode'])
        self.assertNotIn('BWF-VMB', str(evidence))

    def test_yearless_card_never_claims_confirmed_booking(self):
        row = {'dateLabel': 'MI 18 NOV', 'seat': '233A',
               'ticketCode': True, 'ticketReference': True}
        result = summarize_confirmation_candidates([row], '2026-11-18', '233A')
        self.assertTrue(result['existingTicketVisible'])
        self.assertFalse(result['yearVerified'])
        self.assertFalse(result['confirmationVerified'])
        self.assertFalse(result['bookingAuthorized'])

    def test_known_existing_ticket_is_not_bookable(self):
        row = {'dateLabel': 'MI 18 NOV', 'seat': '233A',
               'ticketCode': True}
        result = summarize_inventory_batch([row], ['2026-11-18'],
                                           [{'status': 'account_verified',
                                             'domain': 'westbahn.at'}])
        self.assertTrue(result['days'][0]['potentialDuplicate'])
        self.assertFalse(result['days'][0]['safeToBook'])
        self.assertFalse(result['bookingAuthorized'])

    def test_no_visible_ticket_does_not_authorize_booking(self):
        result = summarize_inventory_batch([], ['2026-11-19'],
                                           [{'status': 'account_verified',
                                             'domain': 'westbahn.at'}])
        self.assertEqual(result['days'][0]['status'], 'review_required')
        self.assertFalse(result['safeToBook'])

if __name__ == '__main__':
    unittest.main()
