import unittest, os, tempfile
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from worker import prepare, official, allowed_navigation, date_url, displayed_date_matches, parse_connection, account_summary, account_audit, account_inventory, inspect_comfort, apply_comfort_control_price, offline_seat_preview, copy_preview_profile, classify_price_audit, safe_request_summary, authenticated_prepare, verify_austrian_session, ensure_austrian_session, trusted_login_url, load_login, select_primary_seat_in_open_modal, seat_modal_state, manual_seat_review, find_open_review_page, is_review_detail_url, ranked_layout_seats, detail_selection_summary, detail_seat_map_entry_check, confirm_review_selection, open_review_seat_map, find_seat_change_control, ACCOUNT_URL, Blocked

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
 def test_auto_open_rejects_nonzero_without_click(self):
  from unittest.mock import Mock
  page=Mock(); page.is_closed.return_value=False; page.context.pages=[page]
  page.evaluate.return_value='https://westbahn.at/reservierung/sitzplatz-upgrade/?do=2026-11-17'
  with patch('worker.read_loaded_connection',return_value={'connection':{'date':'2026-11-17','trainNumber':'1009','departure':'18:22','arrival':'18:49','displayedPriceCents':790,'priceSource':'comfort_control'}}), patch('worker.comfort_control_details') as control:
   with self.assertRaises(Blocked): open_review_seat_map(page,'2026-11-17')
   control.assert_not_called()
 def test_auto_open_uses_existing_modal_without_click(self):
  from unittest.mock import Mock
  page=Mock(); page.is_closed.return_value=False; page.context.pages=[page]
  page.evaluate.return_value='https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt'
  with patch('worker.seat_modal_state',return_value={'modalFound':True}), patch('worker.comfort_control_details') as control:
   self.assertIs(open_review_seat_map(page,'2026-11-17'),page)
   control.assert_not_called()
 def test_confirmation_blocks_unverified_summary(self):
  from unittest.mock import Mock
  page=Mock()
  with patch('worker.detail_selection_summary',return_value={'verified':False}), patch('worker.seat_modal_state') as modal:
   result=confirm_review_selection(page,'2026-11-17')
  self.assertEqual(result['status'],'seat_confirmation_blocked')
  modal.assert_not_called()
 def test_confirmation_never_uses_basket_or_purchase(self):
  from unittest.mock import Mock
  page=Mock(); confirm=Mock()
  selected={'coach':'7','seat':'182A'}
  with patch('worker.detail_selection_summary',side_effect=[{'verified':True},{'verified':True,'seat':'182A','priceCents':0}]), patch('worker.seat_modal_state',side_effect=[{'selected':selected},confirm,{'modalFound':False}]):
   result=confirm_review_selection(page,'2026-11-17')
  self.assertEqual(result['status'],'seat_confirmed')
  self.assertFalse(result['bookingAuthorized'])
  confirm.click.assert_called_once_with(timeout=5000)
 def test_fallback_layout_rejects_four_seat_tables_even_when_two_free(self):
  def seat(code,group,layout,free=True):
   return {'kind':'seat','value':code,'group':group,'layout':layout,'free':free,'disabled':not free}
  controls=[seat('201A','four','single-facing-table'),seat('201B','four','single-facing-table'),seat('202A','four','single-facing-table',False),seat('202B','four','single-facing-table',False),seat('203D','pair','single-facing-table'),seat('204D','pair','single-facing-table',False),seat('205D','offset','single-offset-facing'),seat('206D','offset','single-offset-facing',False),seat('207A','unknown','unknown')]
  self.assertEqual(ranked_layout_seats({'controls':controls}),[(0,'203D'),(1,'205D')])
 def test_fallback_moves_to_known_alternative(self):
  from unittest.mock import Mock
  page=Mock()
  page.evaluate.return_value='https://westbahn.at/reservierung/sitzplatz-upgrade/details'
  coach11=Mock(); coach8=Mock(); seat=Mock()
  current={'coach':'9','seat':'208A','active':'9'}
  coach11.click.side_effect=lambda **kw:current.update(active='11')
  coach8.click.side_effect=lambda **kw:current.update(active='8')
  seat.click.side_effect=lambda **kw:current.update(coach='8',seat='191D')
  def inspect(page,target=None):
   if target:
    return {('coach','11'):coach11,('coach','8'):coach8,('seat','191D'):seat}.get((target['kind'],target['value']))
   return {'modalFound':True,'selected':{'coach':current['coach'],'seat':current['seat']},'activeCoach':current['active'],'comfortMap':True,'controls':[]}
  with patch('worker.seat_modal_state',side_effect=inspect):
   result=select_primary_seat_in_open_modal(page)
  self.assertEqual(result['status'],'alternative_seat_selected')
  self.assertEqual(result['selection'],{'coach':'8','seat':'191D'})
  self.assertFalse(result['bookingAuthorized'])
 def test_manual_seat_review_empty_input_keeps_session_open(self):
  from unittest.mock import Mock
  page=Mock()
  ready={'status':'connection_found','connection':{'displayedPriceCents':0}}
  with patch('worker.authenticated_prepare',return_value=ready) as search, patch('worker.read_review_command',side_effect=['','unknown','a','','q']), patch('worker.find_open_review_page',return_value=(page,{})), patch('worker.select_primary_seat_in_open_modal',return_value={'status':'primary_seat_selected'}) as choose:
   result=manual_seat_review(page,'2026-11-17')
  self.assertEqual(result['status'],'manual_review_ended')
  search.assert_called_once()
  choose.assert_called_once_with(page)
 def test_review_page_uses_live_url_and_unique_modal(self):
  from unittest.mock import Mock
  original=Mock()
  original.is_closed.return_value=False
  original.evaluate.return_value='https://westbahn.at/reservierung/sitzplatz-upgrade/'
  actual=Mock()
  actual.is_closed.return_value=False
  actual.url=original.evaluate.return_value
  actual.evaluate.return_value='https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt'
  original.context.pages=[original,actual]
  with patch('worker.seat_modal_state',return_value={'modalFound':True}):
   chosen,report=find_open_review_page(original,'2026-11-17')
   self.assertIs(chosen,actual)
   self.assertEqual(report['matchingSeatDialogs'],1)
   self.assertIsNone(find_open_review_page(original,'2026-11-18')[0])
   original.context.pages=[original,actual,actual]
   self.assertIsNone(find_open_review_page(original,'2026-11-17')[0])
  self.assertFalse(is_review_detail_url('https://westbahn.at.evil.test/reservierung/sitzplatz-upgrade/details'))
 def test_login_trust_and_no_credentials(self):
  from unittest.mock import Mock
  self.assertTrue(trusted_login_url('https://westbahn.at/anmelden/'))
  self.assertFalse(trusted_login_url('https://westbahn.at.evil.test/anmelden/'))
  self.assertFalse(trusted_login_url('https://westbahn.at@evil.test/anmelden/'))
  with tempfile.TemporaryDirectory() as temp:
   page=Mock()
   with patch('worker.verify_austrian_session',return_value={'status':'login_required'}):
    self.assertEqual(ensure_austrian_session(page,Path(temp))['status'],'login_required')
   page.goto.assert_not_called()
 def test_login_skips_credentials_when_session_valid(self):
  from unittest.mock import Mock
  with patch('worker.verify_austrian_session',return_value={'status':'account_verified'}), patch('worker.load_login') as load:
   self.assertEqual(ensure_austrian_session(Mock(),Path('/unused'))['status'],'account_verified')
   load.assert_not_called()
 def test_login_rejects_insecure_credential_file(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   path=root/'westbahn-login.json'
   path.write_text('{"email":"test@example.org","password":"test-only"}')
   path.chmod(0o644)
   with self.assertRaises(Blocked): load_login(root)
   path.chmod(0o600)
   self.assertEqual(load_login(root)['email'],'test@example.org')
 def test_authenticated_prepare_stops_on_unverified_login(self):
  from unittest.mock import Mock
  page=Mock()
  with patch('worker.verify_austrian_session',return_value={'status':'login_required'}), patch('worker.prepare') as search:
   result=authenticated_prepare(page,'2026-11-17')
  self.assertEqual(result['status'],'login_required')
  search.assert_not_called()
  page.goto.assert_not_called()
 def test_authenticated_prepare_uses_same_page_and_never_authorizes_booking(self):
  from unittest.mock import Mock
  page=Mock()
  page.url='https://westbahn.at/reservierung/sitzplatz-upgrade/'
  with patch('worker.verify_austrian_session',return_value={'status':'account_verified'}) as verify, patch('worker.prepare',return_value={'status':'connection_found','connection':{'displayedPriceCents':0}}) as search:
   result=authenticated_prepare(page,'2026-11-17')
  verify.assert_called_once_with(page)
  search.assert_called_once_with(page,'2026-11-17')
  self.assertTrue(result['accountVerifiedBeforeSearch'])
  self.assertFalse(result['bookingAuthorized'])
 def test_request_summary_redacts_secrets(self):
  from types import SimpleNamespace
  request=SimpleNamespace(url='https://westbahn.at/api/seats/PRIVATE123?token=SECRET',method='GET',resource_type='fetch')
  summary=safe_request_summary(request)
  self.assertEqual(summary['path'],'/api/seats/:redacted')
  self.assertEqual(summary['method'],'GET')
  self.assertTrue(summary['hasQuery'])
  self.assertNotIn('SECRET',str(summary))
  self.assertNotIn('PRIVATE123',str(summary))
  request.url='https://other.example/private?code=SECRET'
  self.assertEqual(safe_request_summary(request)['host'],'other-origin')
 def test_preview_profile_preserves_local_state_and_skips_locks(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   src=root/'source'
   dst=root/'clone'
   (src/'Default'/'IndexedDB').mkdir(parents=True)
   (src/'Default'/'IndexedDB'/'state').write_text('test-only')
   (src/'Default'/'Sessions').mkdir()
   (src/'Default'/'Sessions'/'tabs').write_text('test-only')
   (src/'SingletonLock').write_text('lock')
   copy_preview_profile(src,dst)
   self.assertEqual((dst/'Default'/'IndexedDB'/'state').read_text(),'test-only')
   self.assertFalse((dst/'Default'/'Sessions').exists())
   self.assertFalse((dst/'SingletonLock').exists())
   self.assertTrue((src/'SingletonLock').exists())
 def test_preview_rechecks_price_and_blocks_nonzero(self):
  conn={'displayedPriceCents':790,'priceStatus':'displayed','priceSource':'comfort_control'}
  detail={'targetClassLabels':1,'controls':[{'visible':True,'disabled':False,'pointerEvents':'auto','prices':['€ 7,90']}]}
  with patch('worker.prepare',return_value={'status':'connection_found','connection':conn}), patch('worker.comfort_control_details',return_value=detail):
   result=offline_seat_preview(None,'2026-11-17')
  self.assertEqual(result['status'],'seat_preview_blocked')
  self.assertEqual(result['connection']['displayedPriceCents'],790)
 def test_preview_rejects_stale_zero_when_control_price_disappears(self):
  conn={'displayedPriceCents':0,'priceStatus':'displayed','priceSource':'comfort_control'}
  detail={'targetClassLabels':1,'controls':[{'visible':True,'disabled':False,'pointerEvents':'auto','prices':[]}]}
  with patch('worker.prepare',return_value={'status':'connection_found','connection':conn}), patch('worker.comfort_control_details',return_value=detail):
   result=offline_seat_preview(None,'2026-11-17')
  self.assertEqual(result['status'],'seat_preview_blocked')
  self.assertIsNone(result['connection']['displayedPriceCents'])
 def test_price_audit_distinguishes_context_from_profile(self):
  zero={'priceSamplesCents':[790,0,0]}
  paid={'priceSamplesCents':[790,790]}
  self.assertEqual(classify_price_audit(zero,zero,paid),'restricted_context_price_differs')
  self.assertEqual(classify_price_audit(zero,paid,paid),'profile_copy_price_differs')
  self.assertEqual(classify_price_audit(paid,paid,paid),'normal_browser_zero_not_confirmed')
  self.assertEqual(classify_price_audit(zero,zero,zero),'isolated_zero_observed')
 def test_exact_departure_and_price(self):
  result=parse_connection(RESULTS)
  self.assertEqual(result['trainNumber'],'1009')
  self.assertEqual(result['arrival'],'18:49')
  self.assertEqual(result['displayedPriceCents'],790)
  self.assertFalse(result['priceVerifiedForKlimaTicket'])
 def test_alternate_public_price_formats(self):
  for price,cents in [('0 €',0),('0,00 €',0),('€ 7,90',790),('kostenlos',0),('7.90 €',790)]:
   result=parse_connection(RESULTS.replace('€ 7,90',price))
   self.assertEqual(result['displayedPriceCents'],cents)
   self.assertFalse(result['priceVerifiedForKlimaTicket'])
 def test_inline_departure_and_train_label(self):
  result=parse_connection(RESULTS.replace('Abfahrtszeit,\n','Abfahrtszeit: ').replace('1009\nfährt nach','WB 1009 fährt nach').replace('Ankunftszeit,\n','Ankunftszeit: '))
  self.assertEqual(result['trainNumber'],'1009')
  self.assertEqual(result['arrival'],'18:49')
 def test_price_missing_does_not_use_other_classes(self):
  result=parse_connection(RESULTS.replace('2+ | Comfort\n€ 7,90','2+ | Comfort\nnicht verfügbar'))
  self.assertEqual(result['trainNumber'],'1009')
  self.assertIsNone(result['displayedPriceCents'])
  self.assertEqual(result['priceStatus'],'unavailable')
  self.assertFalse(result['priceVerifiedForKlimaTicket'])
 def test_missing_price_does_not_use_first_class(self):
  result=parse_connection(RESULTS.replace('2+ | Comfort\n€ 7,90','2+ | Comfort'))
  self.assertIsNone(result['displayedPriceCents'])
  self.assertEqual(result['priceStatus'],'not_displayed')
  self.assertEqual(result['comfortAvailability'],'unverified')
 def test_missing_price_still_returns_connection(self):
  result=parse_connection(RESULTS.replace('2+ | Comfort\n€ 7,90','2+ | Comfort\n—'))
  self.assertEqual(result['arrival'],'18:49')
  self.assertIsNone(result['displayedPriceCents'])
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
 def test_primary_seat_modal_detects_existing_selection_without_click(self):
  self.page.set_content("""<section><h2>Sitzplatzreservierung</h2><div>Wagen Platz</div><div>11 233A</div><div>2+ | Comfort</div><button title="233 D nicht verfügbar">233D</button><button>Abbrechen</button><button onclick="window.bought=true">Bestätigen</button></section>""")
  self.assertEqual(seat_modal_state(self.page)['selected'],{'coach':'11','seat':'233A'})
  self.assertIsNone(seat_modal_state(self.page,{'kind':'seat','value':'233D'}))
  self.assertFalse(self.page.evaluate('Boolean(window.bought)'))
 def test_primary_seat_modal_requires_explicit_free_status(self):
  self.page.set_content("""<section><h2>Sitzplatzreservierung</h2><div>Wagen Platz</div><div>11 191D</div><div>2+ | Comfort</div><button title="233 A frei">233A</button><button>233D</button><button>Abbrechen</button><button>Bestätigen</button></section>""")
  self.assertIsNotNone(seat_modal_state(self.page,{'kind':'seat','value':'233A'}))
  self.assertIsNone(seat_modal_state(self.page,{'kind':'seat','value':'233D'}))
 def test_known_seat_enabled_without_free_label_and_svg_comfort(self):
  self.page.set_content("""<section><h2>Sitzplatzreservierung</h2><div>Wagen Platz</div><div>9 208A</div><svg width="200" height="30"><text x="0" y="20">2+ | Comfort</text></svg><button aria-selected="true">8</button><button title="191D">191D</button><button title="182A" disabled>182A</button><button title="205D">205D</button><button>Abbrechen</button><button>Bestätigen</button></section>""")
  state=seat_modal_state(self.page)
  self.assertTrue(state['comfortMap'])
  self.assertEqual(state['activeCoach'],'8')
  self.assertIsNone(seat_modal_state(self.page,{'kind':'seat','value':'191D'}))
  self.assertIsNotNone(seat_modal_state(self.page,{'kind':'seat','value':'191D','allowKnown':True}))
  self.assertIsNone(seat_modal_state(self.page,{'kind':'seat','value':'182A','allowKnown':True}))
  self.assertIsNone(seat_modal_state(self.page,{'kind':'seat','value':'205D','allowKnown':True}))
 def test_detail_comfort_requires_scoped_zero_summary(self):
  self.page.set_content("""<section><h2>Meine Auswahl</h2><p>Reservierung Comfort Class</p><p>Wien Meidling - Wiener Neustadt</p><p>1009 18:22</p><p>€ 0,00</p></section><section><h2>Sitzplatzreservierung</h2><div>Wagen Platz</div><div>9 208A</div><button aria-selected="true">8</button><button>191D</button><button>Abbrechen</button><button>Bestätigen</button></section>""")
  state=seat_modal_state(self.page)
  self.assertFalse(state['comfortMap'])
  self.assertTrue(state['detailComfort'])
  self.page.locator('p').last.evaluate("(e)=>e.textContent='€ 7,90'")
  self.assertFalse(seat_modal_state(self.page)['detailComfort'])
 def test_detail_summary_requires_zero_and_correct_seat(self):
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body='<section><h2>Meine Auswahl</h2><p>Menge Produkt Summe</p><p>1 Reservierung Comfort Class € 0,00</p><p>Wien Meidling - Wiener Neustadt</p><p>1009 Sitzplätze: 182A</p><p>17.11.2026, 18:22–18:49</p><p>€ 0,00</p><button>In den Warenkorb</button></section>'))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  summary=detail_selection_summary(self.page,'2026-11-17','182A')
  self.assertTrue(summary['verified'],summary)
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17','191D')['verified'])
  self.page.locator('p').last.evaluate("(e)=>e.textContent='€ 7,90'")
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17','182A')['verified'])
 def test_detail_summary_handles_split_markup_and_link_control(self):
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body='<main><section><h2>Meine Auswahl</h2><div><span>1</span><span>Reservierung</span><span>Comfort</span><span>Class</span><span>€ 0,00</span></div><p>Wien Meidling – Wiener Neustadt</p><div><span>1009</span><span>Sitzplätze:</span><span>182A</span></div><p>17.11.2026, 18:22 – 18:49</p><span>€ 0,00</span><a href="#">In den Warenkorb</a></section><p>€ 7,90</p></main>'))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  summary=detail_selection_summary(self.page,'2026-11-17','182A')
  self.assertTrue(summary['verified'],summary)
  self.page.locator('section > span').evaluate("(e)=>e.textContent='€ 7,90'")
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17','182A')['verified'])
 def test_detail_summary_expands_sticky_footer_to_product_row(self):
  html='<main><aside><h2>Sitzplatzreservierung</h2><p>€ 7,90 pro Person</p></aside><section><div><h2>Meine Auswahl</h2><p>€ 0,00</p><button>In den Warenkorb</button></div><div><p>1 Reservierung Comfort Class € 0,00</p><p>Wien Meidling – Wiener Neustadt</p><p>1009 Sitzplätze: 182A</p><p>17.11.2026, 18:22 – 18:49</p></div></section></main>'
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  summary=detail_selection_summary(self.page,'2026-11-17','182A')
  self.assertTrue(summary['verified'],summary)
  self.page.locator('section div p').nth(1).evaluate("(e)=>e.textContent='1 Reservierung Comfort Class € 7,90'")
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17','182A')['verified'])
 def test_detail_summary_does_not_expand_into_paid_form(self):
  html='<main><section><h2>Meine Auswahl</h2><p>€ 0,00</p><button>In den Warenkorb</button></section><aside><h2>Sitzplatzreservierung</h2><p>1 Reservierung Comfort Class € 0,00</p><p>Wien Meidling – Wiener Neustadt</p><p>1009 Sitzplätze: 182A</p><p>17.11.2026, 18:22 – 18:49</p></aside></main>'
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17','182A')['verified'])
 def test_seat_map_entry_accepts_zero_footer_separate_from_paid_offer(self):
  html='<main><section><div><h2>Meine Auswahl</h2><p>€ 0,00</p><button>In den Warenkorb</button></div></section><aside><h2>Sitzplatzreservierung</h2><p>Reservierung € 7,90 pro Person</p><p>Wien Meidling – Wiener Neustadt</p><p>1009</p><p>17.11.2026, 18:22–18:49</p></aside></main>'
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  gate=detail_seat_map_entry_check(self.page,'2026-11-17')
  self.assertTrue(gate['verified'],gate)
  self.assertFalse(gate['bookingAuthorized'])
  self.assertFalse(detail_selection_summary(self.page,'2026-11-17')['verified'])
  self.page.locator('section p').evaluate("(e)=>e.textContent='€ 7,90'")
  self.assertFalse(detail_seat_map_entry_check(self.page,'2026-11-17')['verified'])
 def test_seat_map_entry_rejects_mismatching_date_and_duplicate_selection(self):
  html='<main><section><h2>Meine Auswahl</h2><p>€ 0,00</p><button>In den Warenkorb</button></section><h2>Sitzplatzreservierung</h2><p>Wien Meidling – Wiener Neustadt 1009 17.11.2026, 18:22–18:49</p></main>'
  self.page.route('https://westbahn.at/**',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
  self.page.goto('https://westbahn.at/reservierung/sitzplatz-upgrade/details?do=2026-11-17&sf=wien-meidling&st=wiener-neustadt')
  self.assertTrue(detail_seat_map_entry_check(self.page,'2026-11-17')['verified'])
  self.assertFalse(detail_seat_map_entry_check(self.page,'2026-11-18')['verified'])
  self.page.locator('main').evaluate("(e)=>e.insertAdjacentHTML('beforeend','<h2>Meine Auswahl</h2>')")
  self.assertFalse(detail_seat_map_entry_check(self.page,'2026-11-17')['verified'])
 def test_seat_change_finds_unique_buttonless_clickable_label(self):
  self.page.set_content("""<main><section><div class="header"><span>Sitzplatzreservierung</span><span style="cursor:pointer" onclick="window.changed=true">Ändern</span></div><p>Wagen 9 Platz 208A</p></section><aside><h2>Meine Auswahl</h2><button>In den Warenkorb</button><p>Ändern</p></aside></main>""")
  change=find_seat_change_control(self.page)
  self.assertIsNotNone(change,find_seat_change_control(self.page,diagnostic=True))
  change.click()
  self.assertTrue(self.page.evaluate('Boolean(window.changed)'))
 def test_seat_change_finds_anchor_without_href(self):
  self.page.set_content("""<section><div><strong>Sitzplatzreservierung</strong><a onclick="window.changed=true">Ändern</a></div></section>""")
  change=find_seat_change_control(self.page)
  self.assertIsNotNone(change,find_seat_change_control(self.page,diagnostic=True))
  change.click()
  self.assertTrue(self.page.evaluate('Boolean(window.changed)'))
 def test_seat_change_refuses_ambiguous_or_unrelated_control(self):
  self.page.set_content("""<section><div><b>Sitzplatzreservierung</b><a>Ändern</a><a>Ändern</a></div></section>""")
  self.assertIsNone(find_seat_change_control(self.page))
  self.page.set_content("""<section><b>Sitzplatzreservierung</b></section><aside><a>Ändern</a></aside>""")
  self.assertIsNone(find_seat_change_control(self.page))
 def test_seat_editor_uses_only_unique_selected_seat_link_if_change_absent(self):
  self.page.set_content("""<section><div><strong>Sitzplatzreservierung</strong></div><div>Wagen Platz</div><div>9 <a href="#" onclick="window.opened=true">208A</a></div></section><aside><h2>Meine Auswahl</h2><span>208A</span><button>In den Warenkorb</button></aside>""")
  detail=find_seat_change_control(self.page,diagnostic=True)
  self.assertEqual(detail['selectedMode'],'seat_link',detail)
  control=find_seat_change_control(self.page)
  self.assertIsNotNone(control)
  control.click()
  self.assertTrue(self.page.evaluate('Boolean(window.opened)'))
 def test_seat_editor_refuses_noninteractive_or_ambiguous_seat_links(self):
  self.page.set_content("""<section><b>Sitzplatzreservierung</b><div>Wagen Platz</div><p>9 <span>208A</span></p></section>""")
  self.assertIsNone(find_seat_change_control(self.page))
  self.page.set_content("""<section><b>Sitzplatzreservierung</b><div>Wagen Platz</div><a>208A</a><a>191D</a></section>""")
  self.assertIsNone(find_seat_change_control(self.page))
 def test_seat_editor_does_not_use_external_or_unrelated_seat_link(self):
  self.page.set_content("""<section><b>Sitzplatzreservierung</b><p>Wagen Platz</p><a href="https://other.example/">208A</a></section><aside><a>191D</a></aside>""")
  self.assertIsNone(find_seat_change_control(self.page))
 def test_comfort_inspection_is_scoped_and_read_only(self):
  self.page.set_content('<article><div>Abfahrtszeit,</div><div>18:22</div><div>Ankunftszeit,</div><div>18:49</div><div>1009</div><div><button disabled title="ausgebucht">2+ | Comfort</button></div><div><button>1 | First € 10,90</button></div></article><script>window.clicked=0;document.addEventListener("click",()=>window.clicked++)</script>')
  with patch('worker.prepare',return_value={'status':'connection_found','connection':{'trainNumber':'1009'}}):
   result=inspect_comfort(self.page,'2026-11-17')
  self.assertEqual(result['inspection']['targetClassLabels'],1)
  control=result['inspection']['controls'][0]
  self.assertTrue(control['disabled'])
  self.assertEqual(control['prices'],[])
  self.assertIn('ausgebucht',control['availabilityMarkers'])
  self.assertEqual(self.page.evaluate('window.clicked'),0)
 def test_prepare_recovers_price_from_comfort_title(self):
  self.page.evaluate("""() => {
   document.body.insertAdjacentHTML('beforeend','<article><div>Abfahrtszeit,</div><div>18:22</div><div>Ankunftszeit,</div><div>18:49</div><div>1009</div><div>fährt nach Villach</div><div><button title="€ 0,00">2+ | Comfort</button></div><div>1 | First</div><div>€ 10,90</div></article>');
  }""")
  result=prepare(self.page,'2026-11-17')
  self.assertEqual(result['connection']['displayedPriceCents'],0)
  self.assertEqual(result['connection']['priceSource'],'comfort_control')
  self.assertFalse(result['connection']['priceVerifiedForKlimaTicket'])
  self.assertEqual(self.page.evaluate('window.bought'),0)
 def test_control_price_conflict_remains_unknown(self):
  data={'displayedPriceCents':790,'priceStatus':'displayed','priceVerifiedForKlimaTicket':False}
  detail={'targetClassLabels':1,'controls':[{'visible':True,'disabled':False,'pointerEvents':'auto','prices':['€ 0,00']}]}
  result=apply_comfort_control_price(data,detail)
  self.assertIsNone(result['displayedPriceCents'])
  self.assertEqual(result['priceStatus'],'ambiguous')
 def test_offline_seat_preview_does_not_send_click_request(self):
  context=self.b.new_context(service_workers='block')
  try:
   q=context.new_page()
   q.set_content('<article><div>Abfahrtszeit,</div><div>18:22</div><div>Ankunftszeit,</div><div>18:49</div><div>1009</div><div><button title="€ 0,00" onclick="fetch(\'https://westbahn.at/checkout\',{method:\'POST\'}).catch(()=>{});document.body.insertAdjacentHTML(\'beforeend\',\'<button>233 A</button>\')">2+ | Comfort</button></div></article>')
   conn={'trainNumber':'1009','arrival':'18:49','displayedPriceCents':0,'priceSource':'comfort_control'}
   with patch('worker.prepare',return_value={'status':'connection_found','connection':conn}):
    result=offline_seat_preview(q,'2026-11-17')
   self.assertEqual(result['status'],'seat_preview_offline')
   self.assertEqual(result['preferredControls'],[{'seat':'233A','disabled':False}])
   self.assertFalse(result['liveAvailabilityVerified'])
   self.assertIn('blockedRequests',result)
  finally: context.close()
 def test_offline_preview_uses_sibling_label_button(self):
  context=self.b.new_context(service_workers='block')
  try:
   q=context.new_page()
   q.set_content("""<article><div>Abfahrtszeit,</div><div>18:22</div><div>Ankunftszeit,</div><div>18:49</div><div>1009</div><div><span>2+ | Comfort</span><button title="€ 0,00" onclick="document.body.insertAdjacentHTML('beforeend','<button>233 D</button>')">Auswählen</button></div><div><button onclick="window.wrong=true">1 | First € 10,90</button></div></article>""")
   conn={'trainNumber':'1009','arrival':'18:49','displayedPriceCents':0,'priceSource':'comfort_control'}
   with patch('worker.prepare',return_value={'status':'connection_found','connection':conn}):
    result=offline_seat_preview(q,'2026-11-17')
   self.assertEqual(result['preferredControls'],[{'seat':'233D','disabled':False}])
   self.assertFalse(q.evaluate('Boolean(window.wrong)'))
   self.assertFalse(result['liveAvailabilityVerified'])
  finally: context.close()
 def test_network_diagnostic_allows_paid_control_only_offline(self):
  context=self.b.new_context(service_workers='block')
  try:
   q=context.new_page()
   q.set_content("""<article><div>Abfahrtszeit,</div><div>18:22</div><div>Ankunftszeit,</div><div>18:49</div><div>1009</div><div><button title="€ 7,90" onclick="fetch('https://westbahn.at/api/seatmap',{method:'POST'}).catch(()=>{});document.body.insertAdjacentHTML('beforeend','<button>233 A</button>')">2+ | Comfort</button></div></article>""")
   transmitted=[]
   def unexpected(route):
    transmitted.append(route.request.url)
    route.fulfill(status=200,body='unexpected')
   context.route('**/*',unexpected)
   conn={'trainNumber':'1009','arrival':'18:49','displayedPriceCents':790,'priceSource':'comfort_control'}
   with patch('worker.prepare',return_value={'status':'connection_found','connection':conn}):
    result=offline_seat_preview(q,'2026-11-17',network_diagnostic=True)
   self.assertEqual(result['status'],'seat_network_diagnostic')
   self.assertEqual(result['connection']['displayedPriceCents'],790)
   self.assertFalse(result['zeroPriceObserved'])
   self.assertFalse(result['bookingAuthorized'])
   self.assertFalse(result['liveAvailabilityVerified'])
   self.assertEqual(result['preferredControls'],[{'seat':'233A','disabled':False}])
   self.assertEqual(transmitted,[])
  finally: context.close()
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
 def test_regular_inventory_merges_both_domains(self):
  context=self.b.new_context()
  try:
   base='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button>'
   card=lambda day,seat: f'<article><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>{day}</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz {seat}</div></article>'
   common=card('FR 13 NOV','191 D')
   context.route('https://westbahn.de/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=base+common))
   context.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=base+common+card('MO 16 NOV','191 D')))
   result=account_inventory(context,1)
   self.assertEqual(result['status'],'account_verified')
   self.assertEqual(len(result['matchingVisibleCards']),2)
   self.assertEqual(result['matchingVisibleCards'][0]['sources'],['westbahn.at','westbahn.de'])
   self.assertEqual(result['matchingVisibleCards'][1]['sources'],['westbahn.at'])
   self.assertFalse(result['inventoryComplete'])
  finally: context.close()
 def test_regular_inventory_retains_positive_evidence_on_error(self):
  context=self.b.new_context()
  try:
   card='<h1>Westbahn-Konto</h1><button>Gültige Tickets</button><article><h2>Reservierung Comfort Class</h2><div>Abfahrt 18:22 Wien Meidling</div><div>MO 16 NOV</div><div>Ankunft 18:49 Wiener Neustadt</div><div>Sitzplatz 191 D</div></article>'
   context.route('https://westbahn.at/**',lambda route: route.fulfill(status=200,content_type='text/html; charset=utf-8',body=card))
   context.route('https://westbahn.de/**',lambda route: route.fulfill(status=522,body='Timeout'))
   result=account_inventory(context,1)
   self.assertEqual(len(result['matchingVisibleCards']),1)
   self.assertEqual(result['reports'][1]['status'],'http_error')
   self.assertFalse(result['inventoryComplete'])
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
