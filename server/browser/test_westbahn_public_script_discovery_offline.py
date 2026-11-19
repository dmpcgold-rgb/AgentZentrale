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
        self.assertEqual(len(urls),2)
        self.assertEqual(diagnostic["scriptTagCount"],4)
        self.assertEqual(diagnostic["inlineScriptTagCount"],1)
        self.assertEqual(diagnostic["rejectedSources"]["queryOrFragment"],1)
        self.assertEqual(diagnostic["rejectedSources"]["externalHost"],1)
        self.assertEqual(diagnostic["externalScriptHosts"],["cdn.example.net"])
    def test_no_unsafe_fetch(self):
        self.assertFalse(probe.safe_url("https://westbahn.at/a.js?token=secret"))
        self.assertFalse(probe.safe_url("https://evil.example/a.js"))
        self.assertTrue(probe.safe_url("https://westbahn.at/assets/a.js"))
if __name__=="__main__":
    unittest.main()
