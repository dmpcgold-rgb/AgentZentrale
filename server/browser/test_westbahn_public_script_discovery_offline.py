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
        self.assertEqual(diagnostic["queryRetainedForPublicAssets"],1)
        self.assertTrue(any(x.endswith("/assets/v.js?v=1") for x in urls))
        self.assertEqual(sum("?" in x for x in urls),1)
    def test_no_unsafe_fetch(self):
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?token=secret"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?v=1.2.3"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.mjs?ver=20261119"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?group=public&version=20261119"))
        self.assertTrue(probe.safe_url("https://westbahn.at/a.js?disable-minify=false&version=20261119"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?disable-minify=false&version=20261119&token=x"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=1&token=x"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=https%3A%2F%2Fevil.example"))
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?v=1#fragment"))
        self.assertFalse(probe.safe_url("https://evil.example/a.js"))
        self.assertTrue(probe.safe_url("https://westbahn.at/assets/a.js"))
if __name__=="__main__":
    unittest.main()
