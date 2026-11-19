"""Offline tests for safe discovery classification; performs no HTTP."""
import ast
import importlib.util
import unittest
from pathlib import Path

PATH=Path(__file__).with_name("westbahn_public_checkout_script_probe.py")
spec=importlib.util.spec_from_file_location("westbahn_probe",PATH)
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class Discovery(unittest.TestCase):
    def test_valid_python(self):
        ast.parse(PATH.read_text())
    def test_inline_external_and_versioned_scripts(self):
        markup='''<html><script>var x=1</script><script src="/assets/app.js"></script>
        <script src="/assets/v.js?v=1"></script><script src="https://cdn.example.net/app.js"></script>
        <link rel="modulepreload" href="/assets/route.mjs"></html>'''
        urls,diagnostic=probe.discover_assets(markup)
        self.assertEqual(len(urls),3)
        self.assertEqual(diagnostic["scriptTagCount"],4)
        self.assertEqual(diagnostic["inlineScriptTagCount"],1)
        self.assertEqual(diagnostic["rejectedSources"]["queryOrFragment"],0)
        self.assertEqual(diagnostic["rejectedSources"]["externalHost"],1)
        self.assertEqual(diagnostic["externalScriptHosts"],["cdn.example.net"])
        self.assertEqual(diagnostic["allowedVersionedAssets"],1)
        self.assertTrue(any(x.endswith("/assets/v.js?v=1") for x in urls))
        self.assertTrue(any("?" in x for x in urls))
    def test_observed_westbahn_asset_queries(self):
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?group=main&version=123"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?disable-minify=1&version=123"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?disable-minify=1&version=123&token=x"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?group=main&debug=1"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?version=%2Ftmp%2Ffoo"))
    def test_resolve_script_relative_to_html_base(self):
        markup='''<html><head><base href="/"></head><body>
        <script src="build/TicketBooking.a1b2.js?disable-minify=0&amp;version=2"></script>
        </body></html>'''
        urls,diagnostic=probe.discover_assets(markup)
        self.assertEqual(urls,[
            "https://westbahn.at/build/TicketBooking.a1b2.js?disable-minify=0&version=2"
        ])
        self.assertTrue(diagnostic["htmlBasePresent"])
        self.assertTrue(diagnostic["htmlBaseTrusted"])
        self.assertEqual(diagnostic["effectiveBasePath"],"/")
    def test_external_html_base_is_not_followed(self):
        markup='''<html><base href="https://evil.example/">
        <script src="build/TicketBooking.a1b2.js?disable-minify=0&amp;version=2"></script></html>'''
        urls,diagnostic=probe.discover_assets(markup)
        self.assertFalse(diagnostic["htmlBaseTrusted"])
        self.assertTrue(all(u.startswith("https://westbahn.at/") for u in urls))
    def test_no_unsafe_fetch(self):
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?token=secret"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?v=1.2.3"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.mjs?ver=20261119"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=1&token=x"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=https%3A%2F%2Fevil.example"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=1#fragment"))
        self.assertFalse(probe.safe_url("https://evil.example/a.js"))
        self.assertTrue(probe.safe_url("https://westbahn.at/assets/a.js"))
if __name__=="__main__":
    unittest.main()
