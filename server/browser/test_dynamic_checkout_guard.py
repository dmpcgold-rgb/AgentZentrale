import unittest
from unittest.mock import Mock, patch
from dynamic_checkout_guard import audit_dynamic_cart, validate_expected

TRIP = dict(date="2026-11-27", origin="Wien Meidling",
            destination="Wiener Neustadt Hbf", departure="18:22",
            arrival="18:49", train="1009", seat="233A")


def correct():
    return dict(atCheckout=True, titleCount=1, submitCount=1, cardCount=1,
                productCount=1, quantityOne=True, routeMatched=True,
                trainMatched=True, timesMatched=True, dateCount=1,
                dateMatched=True, seatCount=1, seatMatched=True,
                prices=["0,00", "0.00"], zeroTotal=True,
                checkboxCount=1, termsPresent=True, termsAccepted=False)


class DynamicCheckoutTests(unittest.TestCase):
    def test_full_context_is_required(self):
        self.assertEqual(str(validate_expected(TRIP)), "2026-11-27")
        for patch_value in (
            dict(date="2026-11-40"), dict(train=""), dict(seat="233AX"),
            dict(departure="18:2"), dict(arrival="25:00"),
            dict(origin="Wien Meidling", destination="Wien Meidling"),
            dict(origin="<img>"), dict(extra="untrusted")
        ):
            with self.subTest(patch_value=patch_value):
                with patch("dynamic_checkout_guard.dynamic_cart_facts") as browser:
                    result = audit_dynamic_cart(Mock(), dict(TRIP, **patch_value))
                    self.assertFalse(result["verified"])
                    self.assertFalse(result["bookingAuthorized"])
                    browser.assert_not_called()

    def test_dynamic_cart_can_be_verified_read_only_but_never_authorizes_purchase(self):
        with patch("dynamic_checkout_guard.dynamic_cart_facts", return_value=correct()) as browser:
            result = audit_dynamic_cart(Mock(), TRIP)
            self.assertTrue(result["verified"])
            self.assertFalse(result["bookingAuthorized"])
            browser.assert_called_once()

    def test_any_mismatch_fails_closed(self):
        for mismatch in (
            dict(atCheckout=False), dict(titleCount=2), dict(submitCount=2),
            dict(cardCount=0), dict(productCount=2), dict(quantityOne=False),
            dict(routeMatched=False), dict(trainMatched=False),
            dict(timesMatched=False), dict(dateCount=2), dict(dateMatched=False),
            dict(seatCount=2), dict(seatMatched=False),
            dict(prices=["0,00", "5,00"]), dict(prices=[]),
            dict(zeroTotal=False), dict(checkboxCount=2),
            dict(termsPresent=False)
        ):
            with self.subTest(mismatch=mismatch), patch(
                "dynamic_checkout_guard.dynamic_cart_facts",
                return_value=dict(correct(), **mismatch)
            ):
                result = audit_dynamic_cart(Mock(), TRIP)
                self.assertFalse(result["verified"])
                self.assertFalse(result["bookingAuthorized"])

    def test_missing_or_invalid_browser_evidence_fails_closed(self):
        with patch("dynamic_checkout_guard.dynamic_cart_facts", return_value=None):
            self.assertFalse(audit_dynamic_cart(Mock(), TRIP)["verified"])
        with patch("dynamic_checkout_guard.dynamic_cart_facts",
                   side_effect=RuntimeError("unavailable")):
            self.assertEqual(audit_dynamic_cart(Mock(), TRIP)["reason"],
                             "checkout_unreadable")

    def test_terms_never_checked_or_order_clicked_by_guard(self):
        page = Mock()
        with patch("dynamic_checkout_guard.dynamic_cart_facts", return_value=correct()):
            audit_dynamic_cart(page, TRIP)
        page.click.assert_not_called()
        page.locator.assert_not_called()
        page.request.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
