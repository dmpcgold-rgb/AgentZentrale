import unittest
from booking_reference_match import exact_reference_match


class BookingReferenceMatchTests(unittest.TestCase):
    def test_exact_labeled_booking_match_is_case_sensitive(self):
        ticket='Reservierung Comfort Class\nBuchungsnummer: WB-TEST1234'
        self.assertTrue(exact_reference_match(ticket,'WB-TEST1234'))
        self.assertFalse(exact_reference_match(ticket,'wb-test1234'))

    def test_matching_substring_does_not_pass(self):
        ticket='Buchungsnummer: WB-TEST12345'
        self.assertFalse(exact_reference_match(ticket,'WB-TEST1234'))
        self.assertFalse(exact_reference_match(ticket,'TEST12345'))

    def test_unlabeled_token_or_duplicate_conflicting_references_block(self):
        for ticket in (
            'WB-TEST1234',
            'Buchungsnummer: WB-TEST1234 Bestellnummer: WB-OTHER999',
            'Buchungsnummer: WB-TEST1234 Buchungsnummer: WB-OTHER999',
            'Ticketnummer: WB-TEST1234',
            'Buchungsnummer: ',
            ''
        ):
            with self.subTest(ticket_type=len(ticket)):
                self.assertFalse(exact_reference_match(ticket,'WB-TEST1234'))

    def test_invalid_or_missing_expected_reference_never_matches(self):
        text='Buchungsnummer: WB-TEST1234'
        for ref in ('',None,'WB TEST1234','WB-TEST1234!',22,'X'*75):
            with self.subTest(kind=type(ref).__name__):
                self.assertFalse(exact_reference_match(text,ref))


if __name__=='__main__':
    unittest.main()
