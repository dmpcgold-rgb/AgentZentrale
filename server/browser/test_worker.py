import unittest, os
from playwright.sync_api import sync_playwright
from worker import prepare, official, Blocked

HTML='''<label>Von<input id="from"></label><div id="opts1"></div>
<label>Nach<input id="to"></label><div id="opts2"></div>
<label>Hinfahrt<input type="date" id="day"></label>
<button id="search">Verbindung suchen</button><button id="buy">Kaufen</button>
<script>
for(const [id,opts,name] of [['from','opts1','Wien Meidling'],['to','opts2','Wiener Neustadt Hbf']]) {
 const field=document.getElementById(id);field.addEventListener('input',()=>{const opt=document.createElement('button');opt.setAttribute('role','option');opt.textContent=name;opt.onclick=()=>{field.value=name;opt.remove();};document.getElementById(opts).replaceChildren(opt);});
}
window.searched=0;window.bought=0;document.getElementById('search').onclick=()=>window.searched++;document.getElementById('buy').onclick=()=>window.bought++;
</script>'''
class BrowserTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p=sync_playwright().start(); kw={'headless':True}; path=os.getenv('WESTBAHN_CHROMIUM_PATH');
  if path: kw['executable_path']=path
  cls.b=cls.p.chromium.launch(**kw)
 @classmethod
 def tearDownClass(cls): cls.b.close();cls.p.stop()
 def setUp(self): self.page=self.b.new_page(); self.page.set_content(HTML)
 def tearDown(self): self.page.close()
 def test_search_only(self):
  r=prepare(self.page,'2026-11-16');self.assertEqual(r['status'],'search_submitted');self.assertEqual(self.page.evaluate('window.searched'),1);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_no_search_if_ambiguous(self):
  self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<button>Verbindung suchen</button>')")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_wrong_date_type(self):
  self.page.locator('#day').evaluate("e=>e.type='text'")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_domain_allowlist(self):
  self.assertTrue(official('https://westbahn.at/reservierung/'));self.assertFalse(official('https://westbahn.at.evil.example/'));self.assertFalse(official('http://westbahn.at/'));self.assertFalse(official('https://westbahn.at@evil.example/'))
if __name__=='__main__': unittest.main()
