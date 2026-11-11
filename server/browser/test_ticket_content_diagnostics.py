import unittest
from ticket_content_diagnostics import categorize_detail_text


class TicketContentDiagnosticsTests(unittest.TestCase):
    def test_empty_and_client_loading(self):
        for text in ('', 'Loading...', 'Wird geladen, bitte warten'):
            r=categorize_detail_text(text,document_type='html')
            self.assertEqual(r['pageKind'],'empty_or_loading')
            self.assertEqual(r['documentType'],'html')

    def test_login_does_not_count_as_ticket(self):
        r=categorize_detail_text('WESTbahn Anmelden Passwort',document_type='html',
                                 has_password_field=True)
        self.assertEqual(r['pageKind'],'login_required')
        self.assertTrue(r['hasLoginForm'])
        self.assertFalse(r['indicators']['seatLabelVisible'])

    def test_account_overview_is_not_verified_ticket(self):
        r=categorize_detail_text('Westbahn-Konto Gültige Tickets. Weitere Kontofunktionen.', 'html')
        self.assertEqual(r['pageKind'],'account_overview')

    def test_ticket_content_indicators_are_boolean_only(self):
        secret='CONFIDENTIAL-CODE-000987'
        body=('Reservierung Comfort Class Abfahrt: 17.11.2026 18:22 Wien Meidling '
              'Ankunft 18:49 Wiener Neustadt Sitzplatz 191D '
              'Buchungsnummer '+secret)
        r=categorize_detail_text(body, 'html')
        self.assertEqual(r['pageKind'],'ticket_content_present')
        self.assertTrue(all(r['indicators'].values()))
        self.assertNotIn(secret,str(r))
        self.assertNotIn('191D',str(r))

    def test_partial_or_pdf_is_unverified(self):
        partial=categorize_detail_text('Reservierung Comfort Class', 'html')
        self.assertEqual(partial['pageKind'],'partial_ticket_content')
        pdf=categorize_detail_text('', 'html', has_pdf_embed=True)
        self.assertEqual(pdf['pageKind'],'embedded_document')
        self.assertTrue(pdf['hasPdfEmbed'])

    def test_untrusted_document_type_reduced_to_known_vocabulary(self):
        r=categorize_detail_text('Test page', document_type='SUPER-SECRET')
        self.assertEqual(r['documentType'],'unknown')
        self.assertNotIn('SUPER-SECRET',str(r))


if __name__=='__main__':
    unittest.main()
