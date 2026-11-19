"""Offline Playwright DOM regression: no WESTbahn network requests or purchase."""
import os
import unittest
from playwright.sync_api import sync_playwright
from dynamic_checkout_guard import audit_dynamic_cart, dynamic_cart_facts

TRIP = dict(date="2026-11-24", origin="Wien Meidling",
            destination="Wiener Neustadt Hbf", departure="18:22",
            arrival="18:49", train="1009", seat="233A")
HTML = """<!doctype html><html><body><main><section>
<h2>Warenkorb</h2>
<p>Wien Meidling – Wiener Neustadt Hbf</p>
<p>24.11.2026 Zug 1009, 18:22 – 18:49 Uhr</p>
<p>Menge Produkt Summe 1 Reservierung Comfort Class</p>
<p>Sitzplatz: 233A</p>
<p>Einzelpreis € 0,00</p><p>Gesamtsumme € 0,00</p>
<label><input type="checkbox">Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn</label>
<button type="button">Zahlungspflichtig bestellen</button>
</section></main></body></html>"""


class OfflineDynamicDOMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get("WESTBAHN_CHROMIUM_PATH", "")
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
            options["args"] = ["--no-sandbox"]
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_exact_offline_zero_euro_cart_and_mismatches(self):
        page = self.browser.new_page()
        try:
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=HTML))
            page.goto("https://westbahn.at/ticketshop/checkout")
            result = audit_dynamic_cart(page, TRIP)
            self.assertTrue(result["verified"], {"audit":result, "facts":dynamic_cart_facts(page, TRIP), "text":page.locator("section").inner_text()})
            self.assertFalse(result["bookingAuthorized"])
            for patch in (
                dict(date="2026-11-25"), dict(train="1010"),
                dict(departure="18:23"), dict(arrival="18:50"),
                dict(origin="Wien Westbahnhof"),
                dict(destination="Salzburg Hbf"), dict(seat="233D")
            ):
                changed = audit_dynamic_cart(page, dict(TRIP, **patch))
                self.assertFalse(changed["verified"], patch)
                self.assertFalse(changed["bookingAuthorized"])
        finally:
            page.close()

    def test_nonzero_cart_fails(self):
        page = self.browser.new_page()
        try:
            nonzero = HTML.replace("Gesamtsumme € 0,00",
                                   "Gesamtsumme € 5,00")
            page.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html", body=nonzero))
            page.goto("https://westbahn.at/ticketshop/checkout")
            self.assertFalse(audit_dynamic_cart(page, TRIP)["verified"])
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()
