import unittest
from detail_route_diagnostics import route_signature


BASE='https://westbahn.at/ticketshop/dashboard/tickets?page=1&mode=valid'


class RouteSignatureTests(unittest.TestCase):
    def test_private_ids_are_masked(self):
        href='/ticketshop/dashboard/tickets/SECRET-ACCOUNT-12345?ticketid=HIDDEN-999'
        result=route_signature(BASE,href)
        self.assertEqual(result,{'kind':'anchor',
                                 'route':'/ticketshop/dashboard/tickets/[opaque]',
                                 'query':'known_only'})
        self.assertNotIn('SECRET',str(result))
        self.assertNotIn('HIDDEN',str(result))

    def test_other_query_key_and_value_never_leak(self):
        result=route_signature(BASE,'/account/orders/SECRET123?secret_email=PRIVATE@example.org')
        self.assertEqual(result['route'],'/account/orders/[opaque]')
        self.assertEqual(result['query'],'includes_other_keys')
        self.assertNotIn('PRIVATE',str(result))
        self.assertNotIn('secret_email',str(result))

    def test_live_ticket_route_reports_only_coarse_lengths_and_character_class(self):
        short='/ticketshop/dashboard/ticket/ABC123/SECRET-987654321'
        x=route_signature(BASE,short)
        self.assertEqual(x['route'],'/ticketshop/dashboard/ticket/[opaque]/[opaque]')
        self.assertEqual(x['ticketRouteShape'],'4-7|12-90;token_ascii')
        self.assertNotIn('ABC123',str(x))
        self.assertNotIn('SECRET',str(x))
        encoded='/ticketshop/dashboard/ticket/ABC%2F123/SECRET-987654321'
        y=route_signature(BASE,encoded)
        self.assertEqual(y['ticketRouteShape'],'8-11|12-90;other_or_encoded')
        self.assertNotIn('ABC%2F123',str(y))

    def test_only_existing_ticket_two_token_path_has_length_diagnostic(self):
        self.assertNotIn('ticketRouteShape',route_signature(
            BASE,'/account/orders/SECRET123?ticketid=PRIVATE'))
        self.assertNotIn('ticketRouteShape',route_signature(
            BASE,'https://evil.example/ticketshop/dashboard/ticket/SHORT/LONGTOKEN-1234567'))

    def test_different_host_redacted(self):
        result=route_signature(BASE,'https://evil.test/ticketshop/tickets/SECRET')
        self.assertEqual(result['route'],'outside_same_official_host')
        self.assertNotIn('evil.test',str(result))

    def test_buttons_have_no_url(self):
        self.assertEqual(route_signature(BASE,None,'button')['route'],'not_applicable')
        self.assertEqual(route_signature(BASE,'javascript:alert(1)','a')['route'],'outside_same_official_host')

    def test_static_names_are_safely_preserved(self):
        result=route_signature(BASE,'/ticketshop/dashboard/tickets/detail/PRIVATE-ID')
        self.assertEqual(result['route'],'/ticketshop/dashboard/tickets/detail/[opaque]')


if __name__=='__main__':
    unittest.main()
