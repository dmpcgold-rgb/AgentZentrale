import unittest

from klimaticket_eligibility import eligibility_gate, cart_gate


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.observation = {
            'accountVerified': True,
            'dateAndDirectionVerified': True,
            'existingReservation': False,
            'klimaTicketOptionVisible': True,
            'klimaTicketOptionEnabled': True,
            'klimaTicketOptionPriceCents': 0,
        }

    def test_free_search_tile_is_not_enough(self):
        self.assertFalse(eligibility_gate({'displayedPriceCents': 0})['eligible'])

    def test_disabled_zero_euro_option_is_blocked(self):
        self.observation['klimaTicketOptionEnabled'] = False
        self.assertEqual(eligibility_gate(self.observation)['reason'],
                         'klimaticket_option_disabled_or_unknown')

    def test_known_reservation_blocks(self):
        self.observation['existingReservation'] = True
        self.assertEqual(eligibility_gate(self.observation)['reason'],
                         'existing_reservation')

    def test_unknown_inventory_blocks(self):
        self.observation['existingReservation'] = None
        self.assertEqual(eligibility_gate(self.observation)['reason'],
                         'existing_reservation_unknown')

    def test_verified_option_passes_eligibility_only(self):
        self.assertTrue(eligibility_gate(self.observation)['eligible'])


class CartTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'date': '2026-11-19', 'origin': 'Wien Meidling',
                         'destination': 'Wiener Neustadt Hbf',
                         'trainNumber': '1009', 'departure': '18:22',
                         'seat': '208D'}
        self.cart = {**self.expected, 'product': 'Reservierung Comfort Class',
                     'currency': 'EUR', 'totalCents': 0, 'quantity': 1}

    def test_exact_cart_passes_but_never_authorizes_purchase(self):
        result = cart_gate(self.cart, self.expected)
        self.assertTrue(result['valid'])
        self.assertFalse(result['bookingAuthorized'])

    def test_positive_price_blocks(self):
        self.cart['totalCents'] = 100
        self.assertFalse(cart_gate(self.cart, self.expected)['valid'])

    def test_wrong_seat_blocks(self):
        self.cart['seat'] = '191D'
        self.assertFalse(cart_gate(self.cart, self.expected)['valid'])

    def test_missing_total_blocks(self):
        del self.cart['totalCents']
        self.assertFalse(cart_gate(self.cart, self.expected)['valid'])

    def test_boolean_total_blocks(self):
        self.cart['totalCents'] = False
        self.assertFalse(cart_gate(self.cart, self.expected)['valid'])


if __name__ == '__main__':
    unittest.main()
