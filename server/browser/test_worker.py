import unittest, os
from playwright.sync_api import sync_playwright
from worker import prepare, official, allowed_navigation, date_url, displayed_date_matches, parse_connection, account_summary, account_audit, ACCOUNT_URL, Blocked

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

RESULTS = """Abfahrtszeit,
16:22
-
Ankunftszeit,
16:49
Fahrtzeit,
27 Minuten
1007
fährt nach Villach
2 | Standard
€ 1,90
2+ | Comfort
€ 7,90
1 | First
€ 10,90
Abfahrtszeit,
18:22
-
Ankunftszeit,
18:49
Fahrtzeit,
27 Minuten
27m
1009
fährt nach Villach
2 | Standard
€ 1,90
2+ | Comfort
€ 7,90
1 | First
€ 10,90"""
class ResultParsingTests(unittest.TestCase):
 def test_exact_departure_and_price(self):
  result=parse_connection(RESULTS)
  self.assertEqual(result['trainNumber'],'1009')
  self.assertEqual(result['arrival'],'18:49')
  self.assertEqual(result['displayedPriceCents'],790)
  self.assertFalse(result['priceVerifiedForKlimaTicket'])
 def test_duplicate_departures_blocked(self):
  with self.assertRaises(Blocked): parse_connection(RESULTS+'\n'+RESULTS)
 def test_missing_comfort_blocked(self):
  with self.assertRaises(Blocked): parse_connection(RESULTS.replace('2+ | Comfort','Other class'))
 def test_wrong_departure_blocked(self):
  with self.assertRaises(Blocked): parse_connection(RESULTS.replace('18:22','18:23'))

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
 def test_account_summary_read_only(self):
  html='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button><article><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>MO 16 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz 233 A</div><div>Ticketcode SECRET123</div></article>'
  self.page.route('https://westbahn.de/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto(ACCOUNT_URL)
  result=account_summary(self.page)
  self.assertEqual(result['status'],'account_verified')
  self.assertEqual(result['matchingVisibleCards'],[{'dateLabel':'MO 16 NOV','seat':'233A'}])
  self.assertFalse(result['inventoryComplete'])
  self.assertNotIn('SECRET123',str(result))
 def test_account_collects_lazy_loaded_cards(self):
  html="""<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>
  <div id="panel" style="height:120px;overflow-y:auto">
   <article style="height:250px"><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>FR 13 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz 191 D</div></article>
  </div><script>
  const panel=document.getElementById('panel');
  panel.addEventListener('scroll',()=>{
   if(document.getElementById('later'))return;
   panel.insertAdjacentHTML('beforeend','<article id="later"><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>MO 16 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz 191 D</div></article>');
  });
  </script>"""
  self.page.route('https://westbahn.de/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto(ACCOUNT_URL)
  result=account_summary(self.page)
  self.assertEqual(result['newCardsAfterScroll'],1)
  self.assertEqual(len(result['matchingVisibleCards']),2)
  self.assertFalse(result['inventoryComplete'])
 def test_account_audit_finds_ticket_on_second_domain(self):
  context=self.b.new_context()
  try:
   base='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
   card='<article><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>MO 16 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz 191 D</div><div>Ticketcode SECRET123</div></article>'
   context.route('https://westbahn.de/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=base))
   context.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=base+card))
   result=account_audit(context,'2026-11-16')
   self.assertTrue(result['found'])
   self.assertEqual(result['diagnosis'],'reservation_detected')
   self.assertFalse(result['inventoryComplete'])
   self.assertNotIn('SECRET123',str(result))
  finally: context.close()
 def test_account_wrong_page_blocked(self):
  with self.assertRaises(Blocked): account_summary(self.page)
 def test_automatic_results_without_search_button(self):
  self.page.evaluate("(text)=>{const d=document.createElement('pre');d.textContent=text;document.body.append(d);document.getElementById('search').style.display='none'}",RESULTS)
  result=prepare(self.page,'2026-11-17')
  self.assertEqual(result['status'],'connection_found')
  self.assertEqual(result['connection']['trainNumber'],'1009')
  self.assertEqual(self.page.evaluate('window.searched'),0)
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_already_reserved_date_blocked(self):
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-16')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_search_only(self):
  r=prepare(self.page,'2026-11-17');self.assertEqual(r['status'],'search_submitted');self.assertEqual(self.page.evaluate('window.searched'),1);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_wiener_neustadt_operator_alias(self):
  self.page.set_content(HTML.replace('Wiener Neustadt Hbf','Wiener Neustadt'))
  self.assertEqual(prepare(self.page,'2026-11-17')['status'],'search_submitted')
  self.assertEqual(self.page.locator('#to').input_value(),'Wiener Neustadt')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_wrong_destination_rejected(self):
  self.page.set_content(HTML.replace('Wiener Neustadt Hbf','Wiener Neustadt Nord'))
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-17')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_multiple_matching_destinations_rejected(self):
  self.page.evaluate("""document.querySelector('#to').addEventListener('input',()=>{
   const extra=document.createElement('button');extra.setAttribute('role','option');
   extra.textContent='Wiener Neustadt';document.querySelector('#opts2').append(extra);
  })""")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-17')
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
  r=prepare(self.page,'2026-11-17');self.assertEqual(r['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.declined'),1);self.assertEqual(self.page.evaluate('window.accepted'),0)
  self.assertEqual(self.page.evaluate('window.searched'),1);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_unknown_cookie_dialog_fails_closed(self):
  self.page.evaluate("""document.body.insertAdjacentHTML('beforeend','<div id="CybotCookiebotDialog"><button id="CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll">Alle erlauben</button></div>')""")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-17')
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
  self.assertEqual(prepare(self.page,'2026-11-17')['status'],'search_submitted')
  self.assertTrue(self.page.evaluate("Cookiebot.hasResponse && !Cookiebot.consent.marketing && !Cookiebot.consent.statistics && !Cookiebot.consent.preferences"))
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_cookie_navigation_scope(self):
  self.assertTrue(allowed_navigation('https://consentcdn.cookiebot.com/test',True))
  self.assertFalse(allowed_navigation('https://consentcdn.cookiebot.com/test',False))
  self.assertFalse(allowed_navigation('https://evil.example/',True))
 def test_search_link(self):
  self.page.set_content(HTML.replace('<button id="search">Verbindung suchen</button>','<a id="search" href="#search">Verbindung suchen</a>'))
  # Use an official origin to verify the link destination.
  day='2026-11-17'
  html=HTML.replace('<button id="search">Verbindung suchen</button>','<a id="search" href="#search">Verbindung suchen</a>')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto(date_url(day))
  self.assertEqual(prepare(self.page,day)['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.searched'),1)
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_hidden_duplicate_search_ignored(self):
  self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<button hidden>Verbindung suchen</button>')")
  self.assertEqual(prepare(self.page,'2026-11-17')['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.searched'),1)
 def test_alternate_search_caption(self):
  self.page.locator('#search').evaluate("e=>e.textContent='Verbindungen suchen'")
  self.assertEqual(prepare(self.page,'2026-11-17')['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_no_search_if_ambiguous(self):
  self.page.evaluate("document.body.insertAdjacentHTML('beforeend','<button>Verbindung suchen</button>')")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-17')
  self.assertEqual(self.page.evaluate('window.searched'),0);self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_custom_date_picker_from_url(self):
  day='2026-11-17'
  html=HTML.replace('type="date" id="day"','type="text" id="day" readonly value="Di, 17.11.2026"')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto(date_url(day))
  self.assertEqual(prepare(self.page,day)['status'],'search_submitted')
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_custom_date_picker_mismatch_rejected(self):
  day='2026-11-17'
  html=HTML.replace('type="date" id="day"','type="text" id="day" readonly value="Mi, 18.11.2026"')
  self.page.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto(date_url(day))
  with self.assertRaises(Blocked): prepare(self.page,day)
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_date_display_formats(self):
  for value in ('2026-11-17','Di, 17.11.2026','Dienstag, 17. November 2026','Di. 17.11.','17. Nov.'):
   self.assertTrue(displayed_date_matches(value,'2026-11-17',True),value)
  self.assertFalse(displayed_date_matches('17.11.','2026-11-17',False))
  self.assertFalse(displayed_date_matches('17.11.2025','2026-11-17',True))
  self.assertFalse(displayed_date_matches('18.11.','2026-11-17',True))
 def test_wrong_date_type(self):
  self.page.locator('#day').evaluate("e=>e.type='text'")
  with self.assertRaises(Blocked): prepare(self.page,'2026-11-17')
  self.assertEqual(self.page.evaluate('window.searched'),0)
 def test_domain_allowlist(self):
  self.assertTrue(official('https://westbahn.at/reservierung/'));self.assertFalse(official('https://westbahn.at.evil.example/'));self.assertFalse(official('http://westbahn.at/'));self.assertFalse(official('https://westbahn.at@evil.example/'))
if __name__=='__main__': unittest.main()
