import unittest
from unittest.mock import Mock, patch
from checkout_guard import audit_cart

DAY='2026-11-17'
SEAT='191D'


def valid():
    return dict(atCheckout=True,titleCount=1,submitCount=1,cardCount=1,productCount=1,
                checkboxCount=1,termsLabel=True,hasQuantityOne=True,hasComfort=True,
                hasRoute=True,hasTrain=True,hasTime=True,seatCodes=[SEAT],
                dates=['17.11.2026'],prices=['0,00','0,00'],hasTotal=True,buttonDisabled=True)

class AuditTests(unittest.TestCase):
    def test_exact_zero_cart_only(self):
        with patch('checkout_guard.cart_facts',return_value=valid()):
            self.assertTrue(audit_cart(Mock(),DAY,SEAT)['verified'])
            self.assertFalse(audit_cart(Mock(),DAY,SEAT)['bookingAuthorized'])
    def test_wrong_seat_price_or_route_rejected(self):
        for changes in ({'seatCodes':['233A']},{'prices':['0,00','7,90']},
                        {'hasRoute':False},{'hasQuantityOne':False},
                        {'hasTotal':False},{'atCheckout':False},
                        {'dates':['18.11.2026']},{'productCount':2},
                        {'checkboxCount':2},{'submitCount':2}):
            with self.subTest(changes=changes), patch('checkout_guard.cart_facts',return_value=dict(valid(),**changes)):
                self.assertFalse(audit_cart(Mock(),DAY,SEAT)['verified'])
    def test_invalid_input_no_browser_use(self):
        with patch('checkout_guard.cart_facts') as facts:
            self.assertFalse(audit_cart(Mock(),'2026-11-45',SEAT)['verified'])
            self.assertFalse(audit_cart(Mock(),DAY,'bad')['verified'])
            facts.assert_not_called()

if __name__=='__main__': unittest.main()
