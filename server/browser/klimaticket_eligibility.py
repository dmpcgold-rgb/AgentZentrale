"""Fail-closed KlimaTicket eligibility and cart validation.

A zero-price connection tile is never evidence of an available free reservation.
Only explicit selection eligibility and a matching zero-total cart can pass.
This module does not interact with the browser or submit orders.
"""


def eligibility_gate(observation):
    """Return a conservative decision from structured, verified UI evidence."""
    if not isinstance(observation, dict):
        return {'eligible': False, 'reason': 'missing_evidence'}
    if observation.get('accountVerified') is not True:
        return {'eligible': False, 'reason': 'account_unverified'}
    if observation.get('dateAndDirectionVerified') is not True:
        return {'eligible': False, 'reason': 'journey_unverified'}
    if observation.get('existingReservation') is True:
        return {'eligible': False, 'reason': 'existing_reservation'}
    if observation.get('existingReservation') is not False:
        return {'eligible': False, 'reason': 'existing_reservation_unknown'}
    if observation.get('klimaTicketOptionVisible') is not True:
        return {'eligible': False, 'reason': 'klimaticket_option_missing'}
    if observation.get('klimaTicketOptionEnabled') is not True:
        return {'eligible': False, 'reason': 'klimaticket_option_disabled_or_unknown'}
    if observation.get('klimaTicketOptionPriceCents') != 0:
        return {'eligible': False, 'reason': 'klimaticket_option_not_free'}
    return {'eligible': True, 'reason': 'option_verified'}


def cart_gate(cart, expected):
    """Validate cart evidence; this does NOT authorize submitting an order."""
    if not isinstance(cart, dict) or not isinstance(expected, dict):
        return {'valid': False, 'reason': 'missing_evidence', 'bookingAuthorized': False}
    for key in ('date', 'origin', 'destination', 'trainNumber', 'departure', 'seat'):
        if not isinstance(expected.get(key), str) or not expected[key]:
            return {'valid': False, 'reason': 'expected_journey_incomplete', 'bookingAuthorized': False}
        if cart.get(key) != expected[key]:
            return {'valid': False, 'reason': 'cart_journey_mismatch', 'bookingAuthorized': False}
    if cart.get('product') != 'Reservierung Comfort Class':
        return {'valid': False, 'reason': 'cart_product_mismatch', 'bookingAuthorized': False}
    if cart.get('currency') != 'EUR' or type(cart.get('totalCents')) is not int or cart['totalCents'] != 0:
        return {'valid': False, 'reason': 'cart_total_not_zero', 'bookingAuthorized': False}
    if type(cart.get('quantity')) is not int or cart['quantity'] != 1:
        return {'valid': False, 'reason': 'cart_quantity_mismatch', 'bookingAuthorized': False}
    return {'valid': True, 'reason': 'cart_verified', 'bookingAuthorized': False}
