"""Regression checks for read-only WESTbahn detail classification.

Run from repository root:
  python3 -m unittest discover -s server/browser -p 'test_ticket_detail_fallback.py'
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ticket_detail_view import read_detail


class TicketDetailFallbackTests(unittest.TestCase):
    def make_page(self, body):
        page = Mock()
        page.url = 'https://westbahn.at/ticketshop/dashboard/ticket/abcdefgh/1234'
        page.goto.return_value = Mock(status=200, headers={'content-type': 'text/html'})
        page.locator.return_value.inner_text.return_value = body
        page.evaluate.return_value = {'login': False, 'pdf': False}
        return page

    def test_overview_is_not_ticket_evidence(self):
        page = self.make_page('Westbahn-Konto Gültige Tickets Meine Tickets ' * 12)
        with patch('ticket_detail_view.safe_detail_url', return_value=page.url):
            result = read_detail(page, page.url, '2026-11-18', '233A')
        self.assertEqual(result['detailStatus'], 'account_overview_fallback')
        self.assertEqual(result['contentDiagnostics']['pageKind'], 'account_overview')
        self.assertEqual(result['navigationDiagnostics'], {
            'finalHostMatches': True,
            'finalPathMatches': True,
            'finalQueryMatches': True,
        })
        for key in ('yearVerified', 'seatMatched', 'tripMatched',
                    'referenceVisible', 'dateExplicit',
                    'bookingReferenceChecked', 'bookingReferenceMatched'):
            self.assertIs(result[key], False, key)

    def test_overview_fallback_does_not_expose_ticket_identifiers(self):
        page = self.make_page('Westbahn-Konto Gültige Tickets Meine Tickets ' * 12)
        with patch('ticket_detail_view.safe_detail_url', return_value=page.url):
            result = read_detail(page, page.url, '2026-11-18', '233A')
        self.assertNotIn('url', result)
        self.assertNotIn('body', result)
        self.assertNotIn('ticketCode', result)
        self.assertNotIn('abcdefgh', str(result))
        self.assertNotIn('1234', str(result))

    def test_http_error_is_not_a_detail_read(self):
        page = self.make_page('Westbahn-Konto Gültige Tickets')
        page.goto.return_value.status = 403
        with patch('ticket_detail_view.safe_detail_url', return_value=page.url):
            result = read_detail(page, page.url, '2026-11-18', '233A')
        self.assertEqual(result['detailStatus'], 'detail_unavailable')
        self.assertIs(result['yearVerified'], False)

    def test_redirect_to_overview_is_rejected(self):
        page = self.make_page('Westbahn-Konto Gültige Tickets')
        page.url = 'https://westbahn.at/ticketshop/dashboard/tickets'
        with patch('ticket_detail_view.safe_detail_url', side_effect=lambda base, href, caption: href if '/ticket/' in href else None):
            result = read_detail(page, 'https://westbahn.at/ticketshop/dashboard/ticket/abcdefgh/1234',
                                 '2026-11-18', '233A')
        self.assertEqual(result['detailStatus'], 'detail_unavailable')


if __name__ == '__main__':
    unittest.main()
