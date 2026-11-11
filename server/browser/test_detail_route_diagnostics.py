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
