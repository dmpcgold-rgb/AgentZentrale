import unittest, os
from playwright.sync_api import sync_playwright
from worker import prepare, official, allowed_navigation, date_url, displayed_date_matches, Blocked

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
 def test_wiener_neustadt_operator_alias(self):
  self.page.set_content(HTML.replace('Wiener Neustadt Hbf','Wiener Neustadt'))
  self.assertEqual(prepare(self.page,'2026-11-16')['status'],'search_submitted')
  self.assertEqual(self.page.locator('#to').input_value(),'Wiener Neustadt')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_wrong_destination_rejected(self):
  self.page.set_content(HTML.replace('Wiener Neustadt Hbf','Wiener Neustadt Nord'))
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_multiple_matching_destinations_rejected(self):
  self.page.evaluate("""document.querySelector('#to').addEventListener('input',()=>{
   const extra=document.createElement('button');extra.setAttribute('role','option');
   extra.textContent='Wiener Neustadt';document.querySelector('#opts2').append(extra);
  })""")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_cookie_decline_before_search(self):
  self.page.evaluate("""() => {
   document.body.insertAdjacentHTML('beforeend',
    '<div id="CybotCookiebotDialogBodyUnderlay" style="position:fixed;inset:0;z-index:100;background:#ccc"></div>'+
    '<div id="CybotCookiebotDialog" style="position:fixed;top:10px;left:10px;z-index:101">'+
    '<button id="CybotCookiebotDialogBodyButtonDecline">Nur notwendige Cookies</button>'+
    '<button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll">Alle erlauben</button></div>');
   window.declined=0;window.accepted=0;
   document.querySelector('#CybotCookiebotDialogBodyButtonDecline').onclick=()=>{
    window.declined++;document.querySelector('#CybotCookiebotDialog').remove();document.querySelector('#CybotCookiebotDialogBodyUnderlay').remove();
   };
   document.querySelector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll').onclick=()=>window.accepted++;
  }""")
  r=prepare(self.page,'2026-11-16');self.assertEqual(r['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.declined'),1);self.assertEqual(self.page.evaluate('window.accepted'),0)
  self.assertEqual(self.page.evaluate('window.searched'),1);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_unknown_cookie_dialog_fails_closed(self):
  self.page.evaluate("""document.body.insertAdjacentHTML('beforeend','<div id="CybotCookiebotDialog"><button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll">Alle erlauben</button></div>')""")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_cookie_api_fallback(self):
  self.page.evaluate("""() => {
   document.body.insertAdjacentHTML('beforeend',
    '<div id="CybotCookiebotDialogBodyUnderlay" style="position:fixed;inset:0;z-index:100;background:#ccc"></div>'+
    '<div id="CybotCookiebotDialog" style="position:fixed;top:10px;left:10px;z-index:101">'+
    '<button id="CybotCookiebotDialogBodyButtonDecline">Nur notwendige Cookies</button></div>');
   window.Cookiebot={hasResponse:false, consent:{}, submitCustomConsent(p,s,m){
    this.hasResponse=true;this.consent={necessary:true,preferences:p,statistics:s,marketing:m};
   },hide(){document.querySelector('#CybotCookiebotDialog').remove();document.querySelector('#CybotCookiebotDialogBodyUnderlay').remove();}};
  }""")
  self.assertEqual(prepare(self.page,'2026-11-16')['status'],'search_submitted')
  self.assertTrue(self.page.evaluate("Cookiebot.hasResponse && !Cookiebot.consent.marketing && !Cookiebot.consent.statistics && !Cookiebot.consent.preferences"))
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_cookie_navigation_scope(self):
  self.assertTrue(allowed_navigation('https://consentcdn.cookiebot.com/test',True))
  self.assertFalse(allowed_navigation('https://consentcdn.cookiebot.com/test',False))
  self.assertFalse(allowed_navigation('https://evil.example/',True))
 def test_search_link(self):
  self.page.set_content(HTML.replace('<button id="search">Verbindung suchen</button>','<a id="search" href="#search">Verbindung suchen</a>'))
  # Use an official origin to verify the link destination.
  day='2026-11-16'
  html=HTML.replace('<button id="search">Verbindung suchen</button>','<a id="search" href="#search">Verbindung suchen</a>')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html',body=html))
  self.page.goto(date_url(day))
  self.assertEqual(prepare(self.page,day)['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.searched'),1)
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_hidden_duplicate_search_ignored(self):
  self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<button hidden>Verbindung suchen</button>')")
  self.assertEqual(prepare(self.page,'2026-11-16')['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.searched'),1)
 def test_alternate_search_caption(self):
  self.page.locator('#search').evaluate("e=>e.textContent='Verbindungen suchen'")
  self.assertEqual(prepare(self.page,'2026-11-16')['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_no_search_if_ambiguous(self):
  self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<button>Verbindung suchen</button>')")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_custom_date_picker_from_url(self):
  day='2026-11-16'
  html=HTML.replace('type="date" id="day"','type="text" id="day" readonly value="Mo, 16.11.2026"')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html',body=html))
  self.page.goto(date_url(day))
  self.assertEqual(prepare(self.page,day)['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_custom_date_picker_mismatch_rejected(self):
  day='2026-11-16'
  html=HTML.replace('type="date" id="day"','type="text" id="day" readonly value="Di, 17.11.2026"')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html',body=html))
  self.page.goto(date_url(day))
  with self.assertRaises(Blocked): prepare(self.page,day)
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_date_display_formats(self):
  for value in ('2026-11-16','Mo, 16.11.2026','Montag, 16. November 2026','Mo. 16.11.','16. Nov.'):
   self.assertTrue(displayed_date_matches(value,'2026-11-16',True),value)
  self.assertFalse(displayed_date_matches('16.11.','2026-11-16',False))
  self.assertFalse(displayed_date_matches('16.11.2025','2026-11-16',True))
  self.assertFalse(displayed_date_matches('17.11.','2026-11-16',True))
 def test_wrong_date_type(self):
  self.page.locator('#day').evaluate("e=>e.type='text'")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_domain_allowlist(self):
  self.assertTrue(official('https://westbahn.at/reservierung/'));self.assertFalse(official('https://westbahn.at.evil.example/'));self.assertFalse(official('http://westbahn.at/'));self.assertFalse(official('https://westbahn.at@evil.example/'))
if __name__=='__main__': unittest.main()
