import unittest
from unittest.mock import Mock
from ticket_detail_view import safe_detail_url, matching_card, read_detail, inspect_existing_ticket_details

HOME='https://westbahn.at/ticketshop/dashboard/tickets?page=1&mode=valid'
DETAIL='https://westbahn.at/ticketshop/dashboard/tickets/details?id=TESTREF123'
CARD={'text':'Reservierung Comfort Class Abfahrt 18:22 Wien Meidling DI 17 NOV '
              'Ankunft 18:49 Wiener Neustadt Sitzplatz 191D',
      'anchors':[{'caption':'Details','href':'/ticketshop/dashboard/tickets/details?id=TESTREF123'}]}


class TicketDetailTests(unittest.TestCase):
    def test_safe_unique_same_origin_view_link_only(self):
        self.assertEqual(safe_detail_url(HOME,'/ticketshop/dashboard/tickets/details?id=TESTREF123','Details'),DETAIL)
        self.assertEqual(safe_detail_url(HOME,'/ticketshop/dashboard/tickets/ABCDEFGH','Ticket anzeigen'),
                         'https://westbahn.at/ticketshop/dashboard/tickets/ABCDEFGH')
        for url,caption in (
            ('https://evil.test/ticketshop/dashboard/tickets/details?id=1','Details'),
            ('http://westbahn.at/ticketshop/dashboard/tickets/details?id=1','Details'),
            ('https://westbahn.at@evil.test/ticketshop/dashboard/tickets/details?id=1','Details'),
            ('/ticketshop/checkout','Details'),
            ('/ticketshop/dashboard/tickets?page=1&mode=valid','Details'),
            ('/ticketshop/dashboard/tickets/details?id=1&action=cancel','Details'),
            ('/ticketshop/dashboard/tickets/details?id=1','Stornieren'),
            ('/ticketshop/dashboard/tickets/details?id=1','Umbuchen'),
            ('javascript:alert(1)','Details'),
            ('/ticketshop/dashboard/tickets/details?id=1','Bezahlen'),
            ('/ticketshop/dashboard/tickets/details?id=1#buy','Details')
        ):
            with self.subTest(url=url,caption=caption):
                self.assertIsNone(safe_detail_url(HOME,url,caption))

    def test_card_match_requires_trip_date_seat_route_and_time(self):
        self.assertTrue(matching_card(CARD,'2026-11-17','191D'))
        self.assertFalse(matching_card(CARD,'2026-11-18','191D'))
        self.assertFalse(matching_card(CARD,'2026-11-17','233A'))
        self.assertFalse(matching_card({'text':CARD['text'].replace('Wien Meidling','Wien Floridsdorf')},
                                       '2026-11-17','191D'))
        self.assertFalse(matching_card({'text':CARD['text'].replace('Sitzplatz 191D','Sitzplatz 191D Sitzplatz 233A')},
                                       '2026-11-17','191D'))

    def test_detail_read_only_with_explicit_trip_date(self):
        page=Mock()
        page.url='about:blank'
        def go(url,**kw):
            page.url=url
            response=Mock()
            response.status=200
            return response
        page.goto.side_effect=go
        page.locator.return_value.inner_text.return_value=(
            'Reservierung Comfort Class Abfahrt: 17.11.2026 18:22 Wien Meidling '
            'Ankunft 18:49 Wiener Neustadt Sitzplatz: 191D Buchungsnummer: SECRET-123456')
        result=read_detail(page,DETAIL,'2026-11-17','191D')
        self.assertEqual(result['detailStatus'],'detail_read')
        self.assertTrue(result['yearVerified'])
        self.assertTrue(result['referenceVisible'])
        self.assertNotIn('SECRET',str(result))
        page.goto.assert_called_once()
        page.click.assert_not_called()
        page.get_by_role.assert_not_called()
        page.locator.return_value.click.assert_not_called()

    def test_wrong_year_never_verifies(self):
        page=Mock()
        page.url='about:blank'
        def go(url,**kw):
            page.url=url
            response=Mock(status=200)
            response.status=200
            return response
        page.goto.side_effect=go
        page.locator.return_value.inner_text.return_value=(
            'Reservierung Comfort Class Abfahrt: 17.11.2025 18:22 Wien Meidling '
            'Ankunft 18:49 Wiener Neustadt Sitzplatz: 191D')
        result=read_detail(page,DETAIL,'2026-11-17','191D')
        self.assertFalse(result['yearVerified'])

    def test_invalid_input_returns_blocked_without_opening_account(self):
        ctx=Mock()
        result=inspect_existing_ticket_details(ctx,'2026-11-99','191D')
        self.assertEqual(result['detailStatus'],'invalid_date')
        self.assertFalse(result['confirmationVerified'])
        self.assertFalse(result['safeToBook'])
        ctx.new_page.assert_not_called()


class TicketDetailBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from playwright.sync_api import sync_playwright
        cls.p=sync_playwright().start()
        kw={'headless':True}
        executable=os.environ.get('WESTBAHN_CHROMIUM_PATH')
        if executable:kw['executable_path']=executable
        cls.browser=cls.p.chromium.launch(**kw)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def test_gets_unique_read_only_detail_without_click(self):
        context=self.browser.new_context()
        visited=[]
        try:
            account=('''<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
            <article><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div>
            <div>DI 17 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div>
            <div>Sitzplatz 191D</div>
            <a href="/ticketshop/dashboard/tickets/details?id=TESTREF123">Details</a>
            <button onclick="window.bought=true">Zahlungspflichtig bestellen</button></article>''')
            details=('''<h1>Reservierung Comfort Class</h1><p>Abfahrt: 17.11.2026 18:22 Wien Meidling</p>
            <p>Ankunft 18:49 Wiener Neustadt</p><p>Sitzplatz: 191D</p>
            <p>Buchungsnummer: SECRET-123456</p>''')
            def route_handler(route):
                visited.append((route.request.method,route.request.url))
                if '/tickets/details' in route.request.url:
                    body=details
                elif 'westbahn.at' in route.request.url:
                    body=account
                else:
                    body='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=body)
            context.route('https://westbahn.at/**',route_handler)
            context.route('https://westbahn.de/**',route_handler)
            result=inspect_existing_ticket_details(context,'2026-11-17','191D',max_pages=1)
            self.assertEqual(result['detailStatus'],'detail_read',result)
            self.assertTrue(result['yearVerified'])
            self.assertFalse(result['confirmationVerified'])
            self.assertFalse(result['bookingAuthorized'])
            self.assertNotIn('SECRET',str(result))
            self.assertTrue(all(method=='GET' for method,_ in visited))
            self.assertFalse(any('/checkout' in url for _,url in visited))
        finally:
            context.close()

    def test_opaque_button_never_clicked(self):
        context=self.browser.new_context()
        try:
            account=('''<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
            <article><h2>Reservierung Comfort Class</h2><p>Abfahrt 18:22 Wien Meidling DI 17 NOV</p>
            <p>Ankunft 18:49 Wiener Neustadt</p><p>Sitzplatz 191D</p>
            <button onclick="window.rebooked=true">Details</button></article>''')
            def route_handler(route):
                html=account if 'westbahn.at' in route.request.url else '<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
            context.route('https://westbahn.at/**',route_handler)
            context.route('https://westbahn.de/**',route_handler)
            result=inspect_existing_ticket_details(context,'2026-11-17','191D',max_pages=1)
            self.assertEqual(result['detailStatus'],'no_unique_safe_detail_link',result)
            self.assertFalse(result['bookingAuthorized'])
        finally:
            context.close()


if __name__=='__main__':
    unittest.main()
