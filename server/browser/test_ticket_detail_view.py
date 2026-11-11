import unittest
from unittest.mock import Mock
from ticket_detail_view import safe_detail_url, matching_card, read_detail, inspect_existing_ticket_details, rejection_reason

HOME='https://westbahn.at/ticketshop/dashboard/tickets?page=1&mode=valid'
DETAIL='https://westbahn.at/ticketshop/dashboard/tickets/details?id=TESTREF123'
CARD={'text':'Reservierung Comfort Class Abfahrt 18:22 Wien Meidling DI 17 NOV '
              'Ankunft 18:49 Wiener Neustadt Sitzplatz 191D',
      'anchors':[{'caption':'Details','href':'/ticketshop/dashboard/tickets/details?id=TESTREF123'}]}


class TicketDetailTests(unittest.TestCase):
    def test_module_syntax_and_no_duplicate_functions(self):
        import ast
        from pathlib import Path
        source=Path(__file__).with_name('ticket_detail_view.py').read_text(encoding='utf-8')
        tree=ast.parse(source,filename='ticket_detail_view.py')
        names=[node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(len(names),len(set(names)),names)

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

    def test_actual_two_opaque_segment_ticket_route_is_strictly_read_only(self):
        # This path SHAPE was observed on the live account; the identifiers below are fake.
        valid='/ticketshop/dashboard/ticket/FAKE-TICKET-12345678/FAKE-VIEW-987654321'
        self.assertEqual(safe_detail_url(HOME,valid,'Details'),'https://westbahn.at'+valid)
        self.assertEqual(safe_detail_url(HOME,valid,'Ticket anzeigen'),'https://westbahn.at'+valid)
        for href,label in (
            (valid,'Umbuchen'),
            (valid,'Bearbeiten'),
            (valid,'Buchung kaufen'),
            (valid,'Völlig unbekannte Aktion'),
            (valid+'?action=view','Details'),
            (valid+'#details','Details'),
            ('/ticketshop/dashboard/ticket/cancel/FAKE-VIEW-987654321','Details'),
            ('/ticketshop/dashboard/ticket/FAKE-TICKET-12345678/rebook-FAKE12345','Details'),
            ('/ticketshop/dashboard/ticket/FAKE-TICKET-12345678/stornieren1234','Details'),
            ('/ticketshop/dashboard/ticket/SHORT/FAKE-VIEW-987654321','Details'),
            ('https://westbahn.de'+valid,'Details'),
            ('https://evil.example'+valid,'Details'),
        ):
            with self.subTest(href=href,label=label):
                self.assertIsNone(safe_detail_url(HOME,href,label))

    def test_rejected_detail_controls_report_only_fixed_categories(self):
        cases=(
            ({'tag':'a','href':'#','caption':'Details'},'no_static_destination'),
            ({'tag':'button','href':None,'caption':'Details'},'non_link_detail_control'),
            ({'tag':'a','href':'/ticketshop/dashboard/tickets/details?session=PRIVATE-9199',
              'caption':'Details'},'unrecognized_query'),
            ({'tag':'a','href':'/account/order/PRIVATE-9199','caption':'Details'},'unrecognized_detail_path'),
            ({'tag':'a','href':'https://evil.example/ticketshop/dashboard/tickets/PRIVATE-9199',
              'caption':'Details'},'untrusted_destination'),
            ({'tag':'a','href':'javascript:alert(1)','caption':'Details'},'script_or_data_destination'),
            ({'tag':'a','href':'/ticketshop/dashboard/tickets/details?id=PRIVATE-9199',
              'caption':'Umbuchen'},'unsafe_action_label')
        )
        for item,reason in cases:
            with self.subTest(reason=reason):
                result=rejection_reason(HOME,item)
                self.assertEqual(result,reason)
                self.assertNotIn('PRIVATE',result)
        self.assertEqual(rejection_reason(HOME,{'tag':'a',
            'href':'/ticketshop/dashboard/tickets/details?id=PRIVATE-9199',
            'caption':'Details'}),'accepted')

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
            self.assertTrue(any(method=='GET' and '/tickets/details' in url for method,url in visited),
                            'Mock detail handler was bypassed')
            self.assertFalse(result['confirmationVerified'])
            self.assertFalse(result['bookingAuthorized'])
            self.assertNotIn('SECRET',str(result))
            self.assertTrue(all(method=='GET' for method,_ in visited))
            self.assertFalse(any('/checkout' in url for _,url in visited))
        finally:
            context.close()

    def test_unknown_detail_route_is_masked_and_never_opened(self):
        context=self.browser.new_context()
        visited=[]
        try:
            account=('''<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
            <article><h2>Reservierung Comfort Class</h2>
            <p>Abfahrt 18:22 Wien Meidling DI 17 NOV</p>
            <p>Ankunft 18:49 Wiener Neustadt</p><p>Sitzplatz 191D</p>
            <a href="/account/orders/PRIVATE-9876?user_email=PRIVATE@example.org">Details</a></article>''')
            def serve(route):
                visited.append(route.request.url)
                body=account if 'westbahn.at' in route.request.url else '<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=body)
            context.route('https://westbahn.at/**',serve)
            context.route('https://westbahn.de/**',serve)
            result=inspect_existing_ticket_details(context,'2026-11-17','191D',max_pages=1)
            self.assertEqual(result['detailStatus'],'no_unique_safe_detail_link')
            self.assertEqual(result['candidatePathPatterns'][0]['route'],'/account/orders/[opaque]')
            self.assertEqual(result['candidatePathPatterns'][0]['query'],'includes_other_keys')
            self.assertNotIn('PRIVATE',str(result))
            self.assertFalse(any('/account/orders/' in url for url in visited))
        finally:
            context.close()

    def test_observed_detail_route_get_only_no_purchase(self):
        context=self.browser.new_context()
        touched=[]
        fake='/ticketshop/dashboard/ticket/FAKE-TICKET-12345678/FAKE-VIEW-987654321'
        try:
            account=('''<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
            <article><h2>Reservierung Comfort Class</h2><p>Abfahrt 18:22 Wien Meidling DI 17 NOV</p>
            <p>Ankunft 18:49 Wiener Neustadt</p><p>Sitzplatz 191D</p>
            <a href="'''+fake+'''">Details</a>
            <button onclick="fetch('/ticketshop/checkout',{method:'POST'})">Zahlungspflichtig bestellen</button></article>''')
            detail=('''<h1>Reservierung Comfort Class</h1><p>Abfahrt: 17.11.2026 18:22 Wien Meidling</p>
            <p>Ankunft 18:49 Wiener Neustadt</p><p>Sitzplatz: 191D</p>
            <p>Buchungsnummer: CONFIDENTIAL-12345</p>
            <script>fetch('/ticketshop/checkout',{method:'POST'}).catch(()=>{});</script>''')
            def serve(route):
                touched.append((route.request.method,route.request.url))
                if fake in route.request.url:
                    body=detail
                elif 'westbahn.at' in route.request.url:
                    body=account
                else:
                    body='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=body)
            context.route('https://westbahn.at/**',serve)
            context.route('https://westbahn.de/**',serve)
            result=inspect_existing_ticket_details(context,'2026-11-17','191D',max_pages=1)
            self.assertEqual(result['detailStatus'],'detail_read',result)
            self.assertTrue(result['yearVerified'])
            self.assertTrue(any(method=='GET' and fake in url for method,url in touched),
                            'Mock ticket route handler was bypassed')
            self.assertFalse(result['confirmationVerified'])
            self.assertFalse(result['bookingAuthorized'])
            self.assertNotIn('CONFIDENTIAL',str(result))
            self.assertFalse(any(method=='POST' for method,url in touched))
            self.assertFalse(any('/ticketshop/checkout' in url for method,url in touched))
        finally:
            context.close()

    def test_short_unknown_ticket_path_is_not_navigated_but_diagnosed(self):
        context=self.browser.new_context()
        visits=[]
        try:
            target='/ticketshop/dashboard/ticket/SHORT99/SECRET-LONG-123456789'
            account=('''<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
                <article><h2>Reservierung Comfort Class</h2>
                <p>Abfahrt 18:22 Wien Meidling DI 17 NOV</p>
                <p>Ankunft 18:49 Wiener Neustadt Sitzplatz 191D</p>
                <a href="'''+target+'''">Details</a></article>''')
            def serve(route):
                visits.append(route.request.url)
                html=account if 'westbahn.at' in route.request.url else '<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
                route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html)
            context.route('https://westbahn.at/**',serve)
            context.route('https://westbahn.de/**',serve)
            result=inspect_existing_ticket_details(context,'2026-11-17','191D',max_pages=1)
            self.assertEqual(result['detailStatus'],'no_unique_safe_detail_link')
            self.assertEqual(result['candidatePathPatterns'][0]['ticketRouteShape'],'4-7|12-90;token_ascii')
            self.assertFalse(any(target in url for url in visits))
            self.assertNotIn('SECRET-LONG',str(result))
            self.assertFalse(result['bookingAuthorized'])
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
            self.assertEqual(result['rejectionReasons'],{'non_link_detail_control':1})
            self.assertEqual(result['controlKinds'],{'button':1})
        finally:
            context.close()


if __name__=='__main__':
    unittest.main()
