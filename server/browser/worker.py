#!/usr/bin/env python3
"""Private WESTbahn browser. Read-only search; no checkout or payment actions."""
import argparse, fcntl, json, os, sys, re
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit, parse_qs, urlencode
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = 'https://westbahn.at/reservierung/sitzplatz-upgrade/'
ORIGIN = 'Wien Meidling'
DESTINATION = 'Wiener Neustadt Hbf'

class Blocked(Exception): pass

def official(url):
    p=urlsplit(url)
    return p.scheme=='https' and (p.hostname=='westbahn.at' or (p.hostname or '').endswith('.westbahn.at')) and not p.username and not p.password

def allowed_navigation(url, subframe=False):
    if official(url): return True
    p=urlsplit(url)
    return (subframe and p.scheme=='https' and not p.username and not p.password
            and p.hostname in ('consent.cookiebot.com','consentcdn.cookiebot.com','consent.cookiebot.eu','consentcdn.cookiebot.eu'))

def unique(candidates, name):
    for loc in candidates:
        if loc.count()==1 and loc.is_visible(): return loc
    raise Blocked(f'Feld nicht eindeutig: {name}. Bitte Ticketshop im Browser prüfen.')

def dismiss_cookie_dialog(page, wait_ms=3000):
    # Use the provider's explicit opt-out, not DOM manipulation or accept-all.
    dialog = page.locator('#CybotCookiebotDialog')
    underlay = page.locator('#CybotCookiebotDialogBodyUnderlay')
    try:
        dialog.wait_for(state='visible', timeout=wait_ms)
    except PWTimeout:
        if not underlay.is_visible(): return False
        raise Blocked('Cookie-Overlay sichtbar, aber Dialog nicht eindeutig erreichbar.')
    if dialog.count()!=1: raise Blocked('Cookie-Dialog nicht eindeutig.')
    candidates = [
        dialog.locator('#CybotCookiebotDialogBodyButtonDecline'),
        dialog.locator('#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll'),
    ]
    buttons = [loc for loc in candidates if loc.count()==1 and loc.is_visible()]
    if len(buttons)!=1:
        raise Blocked('Cookie-Dialog: keine eindeutige Schaltfläche zum Ablehnen optionaler Cookies.')
    # First use the real opt-out button. A transparent overlay may remain in
    # the DOM; test actual form actionability instead of its mere visibility.
    try:
        buttons[0].click(timeout=5000)
        field(page, 'Von').click(trial=True, timeout=5000)
        return True
    except PWTimeout:
        pass
    # Cookiebot's documented consent API is a second, explicit opt-out.
    # Never forge cookies, remove overlays, or accept optional categories.
    try:
        if not page.evaluate("typeof window.Cookiebot?.submitCustomConsent === 'function'"):
            raise Blocked('Cookie-Ablehnung: Klick oder Formular blockiert; Cookiebot-API nicht verfügbar.')
        page.evaluate("window.Cookiebot.submitCustomConsent(false, false, false)")
        page.wait_for_function("""() => {
            const c = window.Cookiebot;
            return c?.hasResponse === true && c.consent?.necessary === true &&
                c.consent.preferences === false && c.consent.statistics === false &&
                c.consent.marketing === false;
        }""", timeout=8000)
        # Hide the provider's dialog only after a verified necessary-only response.
        page.evaluate("if (typeof window.Cookiebot.hide === 'function') window.Cookiebot.hide()")
        field(page, 'Von').click(trial=True, timeout=5000)
    except PWTimeout:
        raise Blocked('Cookie-Ablehnung nicht bestätigt oder Suchformular weiterhin blockiert. Keine Suche ausgeführt.')
    return True

def field(page, label):
    return unique([page.get_by_label(label,exact=True),page.get_by_placeholder(label,exact=True)],label)

# The operator's timetable labels this stop "Wiener Neustadt"; the
# station's full name is Wiener Neustadt Hauptbahnhof. No other stops qualify.
STATION_LABELS = {
    ORIGIN: ('Wien Meidling',),
    DESTINATION: ('Wiener Neustadt', 'Wiener Neustadt Hbf',
                  'Wiener Neustadt Hauptbahnhof', 'Wr. Neustadt Hbf'),
}
def normalize_station(value):
    return ' '.join(value.split()).casefold()

def set_station(page,label,value):
    loc=field(page,label)
    names=STATION_LABELS[value]
    accepted={normalize_station(n) for n in names}
    # Search by the common base name, without a suffix that may not exist in
    # WESTbahn's autocomplete. Accept only exact known aliases, never a prefix.
    loc.fill(names[0])
    pattern=re.compile(r'^(?:' + '|'.join(re.escape(n).replace(r'\ ',r'\s+') for n in names) + r')$',re.IGNORECASE)
    option=page.get_by_role('option',name=pattern)
    try:
        option.first.wait_for(state='visible',timeout=7000)
    except PWTimeout:
        visible=page.get_by_role('option').all()
        suggestions=[o.inner_text(timeout=1000).strip()[:100] for o in visible[:12] if o.is_visible()]
        detail=' Vorschläge: '+', '.join(suggestions) if suggestions else ' Keine sichtbaren Vorschläge.'
        raise Blocked(f'Bahnhofsvorschlag für {label} nicht eindeutig bestätigt.{detail}')
    if option.count()!=1: raise Blocked(f'Mehrdeutiger Bahnhofsvorschlag: {label}.')
    option.click(timeout=5000)
    if normalize_station(loc.input_value()) not in accepted:
        raise Blocked(f'Bahnhof {label} nicht bestätigt.')

def date_url(day):
    # The public reservation form uses "do" for outbound date and "tv=a"
    # for one-way journeys. Still verify the rendered field before search.
    return URL + '?' + urlencode({'tv':'a','do':date.fromisoformat(day).isoformat()})

def displayed_date_matches(value, day, query_verified=False):
    expected=date.fromisoformat(day)
    value=' '.join(value.split()).strip().casefold()
    if value==day: return True
    # German weekday labels, numeric dates, or German month names.
    value=re.sub(r'^(?:mo(?:ntag)?|di(?:enstag)?|mi(?:ttwoch)?|do(?:nnerstag)?|fr(?:eitag)?|sa(?:mstag)?|so(?:nntag)?)\.?\s*,?\s+', '', value)
    match=re.fullmatch(r'(\d{1,2})[./]\s*(\d{1,2})(?:[./]\s*(\d{4}))?\.?',value)
    if match:
        d,m,y=match.groups()
        return int(d)==expected.day and int(m)==expected.month and (int(y)==expected.year if y else query_verified)
    months={'jan':1,'januar':1,'jän':1,'jänner':1,'feb':2,'februar':2,'mär':3,'märz':3,'mrz':3,'apr':4,'april':4,'mai':5,'jun':6,'juni':6,'jul':7,'juli':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'okt':10,'oktober':10,'nov':11,'november':11,'dez':12,'dezember':12}
    match=re.fullmatch(r'(\d{1,2})\.?\s+([a-zä]+)\.?(?:\s+(\d{4}))?',value)
    if match:
        d,m,y=match.groups()
        return int(d)==expected.day and months.get(m)==expected.month and (int(y)==expected.year if y else query_verified)
    return False

def confirm_date(page, day):
    when=field(page,'Hinfahrt')
    if when.get_attribute('type')=='date':
        when.fill(day)
        if when.input_value()!=day: raise Blocked('Datum nicht bestätigt.')
        return
    # Custom date picker: never inject a value into the DOM or bypass events.
    # Its date was requested through the official public form URL.
    query_ok=official(page.url) and parse_qs(urlsplit(page.url).query).get('do')==[day]
    value=when.evaluate("(el) => typeof el.value === 'string' ? el.value : (el.textContent || '')").strip()
    if not query_ok or not displayed_date_matches(value,day,query_verified=query_ok):
        detail=' '.join(value.split())[:100] or '(leer)'
        raise Blocked(f'Datum {day} nicht bestätigt. Kalender zeigt: {detail}. Datumsparameter: {"passend" if query_ok else "abweichend"}. Keine Suche.')
    
SEARCH_NAMES = re.compile(r'^\s*(?:Verbindung(?:en)? suchen|Z(?:ug|üge) suchen|Verbindung(?:en)? anzeigen|Züge anzeigen)\s*$', re.IGNORECASE)

def search_control(page):
    # Match only explicit connection-search actions, never checkout or payment.
    # The ticket shop may render its search as a button, submit input or link.
    candidates=page.get_by_role('button', name=SEARCH_NAMES).or_(page.get_by_role('link', name=SEARCH_NAMES))
    # Some custom controls expose the caption visually but not as an accessible name.
    candidates=candidates.or_(page.locator('button, a, [role="button"], [role="link"]').filter(has_text=SEARCH_NAMES))
    # A generic "Suchen" is only safe inside the same actual form as all
    # three trip fields, not the site's navigation or global search.
    form=field(page,'Von').locator('xpath=ancestor::form[1]')
    if form.count()==1 and form.get_by_label('Nach',exact=True).or_(form.get_by_placeholder('Nach',exact=True)).count()==1 and form.get_by_label('Hinfahrt',exact=True).or_(form.get_by_placeholder('Hinfahrt',exact=True)).count()==1:
        candidates=candidates.or_(form.get_by_role('button',name='Suchen',exact=True))
    try:
        candidates.filter(visible=True).first.wait_for(state='visible',timeout=5000)
    except PWTimeout:
        pass
    visible=candidates.filter(visible=True)
    if visible.count()!=1:
        # Report actual public control captions, without credentials, page HTML or cookies.
        labels=page.locator('button, a, [role="button"], [role="link"], input[type="submit"]').evaluate_all("""els => els.filter(e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden').map(e => (e.getAttribute('aria-label') || e.innerText || e.value || e.getAttribute('title') || '').trim().replace(/\\s+/g,' ')).filter(t => t && /such|find|verbind|zug|reserv|weiter|anzeigen/i.test(t)).slice(0,20)""")
        detail=' | '.join(dict.fromkeys(labels))[:500] or 'keine passenden sichtbaren Bedienelemente'
        raise Blocked(f'Suchbutton nicht eindeutig ({visible.count()} Treffer). Gefunden: {detail}. Keine Suche.')
    control=visible.first
    # Links may open a search route but never navigate to a foreign domain.
    href=control.evaluate("(e) => e.tagName === 'A' ? e.href : ''")
    if href and not official(href):
        raise Blocked('Suchlink verweist nicht auf WESTbahn. Keine Suche.')
    if not control.is_enabled(): raise Blocked('Suchbutton ist deaktiviert. Keine Suche.')
    return control



# The reservation page populates connection results when the trip fields change.
# Parse the visible departure blocks, not a global occurrence of "18:22".
DEPARTURE_MARKER = re.compile(r'(?im)^[ \t]*Abfahrtszeit,?[ \t]*$')
TIME_LINE = r'(?:[01]\d|2[0-3]):[0-5]\d'

def parse_connection(text):
    lines = '\n'.join(' '.join(line.split()) for line in text.splitlines())
    blocks = DEPARTURE_MARKER.split(lines)[1:]
    matches = []
    for block in blocks:
        departure = re.match(r'^\s*(' + TIME_LINE + r')\b', block)
        if not departure or departure.group(1) != '18:22':
            continue
        matches.append(block)
    if len(matches) != 1:
        raise Blocked(f'Abfahrt 18:22 nicht eindeutig ({len(matches)} Treffer). Keine Buchung.')
    block = matches[0]
    arrivals = re.findall(r'(?im)^Ankunftszeit,?\s*(' + TIME_LINE + r')\s*$', block)
    trains = re.findall(r'(?im)^(?:WB\s*)?(\d{3,5})\s*\n\s*fährt nach[ \t]+([^\n]+)$', block)
    comfort = re.findall(r'(?im)^2\+\s*\|\s*Comfort(?: Class)?\s*\n\s*€\s*(\d+(?:[.,]\d{2}))\s*$', block)
    if len(arrivals) != 1 or len(trains) != 1 or len(comfort) != 1:
        raise Blocked('Zugnummer, Ankunft oder Comfort-Preis nicht eindeutig auslesbar. Keine Buchung.')
    train, direction = trains[0]
    cents = int(comfort[0].replace(',', '').replace('.', ''))
    return {'departure':'18:22','arrival':arrivals[0],'trainNumber':train,
            'direction':direction.strip(),'class':'2+','displayedPriceCents':cents,
            'currency':'EUR','priceVerifiedForKlimaTicket':False}

def read_loaded_connection(page, day):
    try:
        page.wait_for_function(r"""() => /Abfahrtszeit,?\s*\n\s*18:22\b/i.test(document.body.innerText)""",timeout=8000)
    except PWTimeout:
        pass
    text=page.locator('body').inner_text(timeout=5000)
    if not DEPARTURE_MARKER.search(text):
        return None
    found=parse_connection(text)
    # Recheck trip inputs after the asynchronous result load.
    for label, station in [('Von',ORIGIN),('Nach',DESTINATION)]:
        if normalize_station(field(page,label).input_value()) not in {normalize_station(n) for n in STATION_LABELS[station]}:
            raise Blocked('Bahnhofsauswahl hat sich geändert. Keine Buchung.')
    when=field(page,'Hinfahrt')
    if when.get_attribute('type')=='date':
        date_ok=when.input_value()==day
    else:
        value=when.evaluate("(el) => typeof el.value === 'string' ? el.value : (el.textContent || '')")
        date_ok=official(page.url) and parse_qs(urlsplit(page.url).query).get('do')==[day] and displayed_date_matches(value,day,True)
    if not date_ok:
        raise Blocked('Reisedatum hat sich geändert. Keine Buchung.')
    price=f"{found['displayedPriceCents']/100:.2f}".replace('.',',')
    return {'status':'connection_found','connection':{'date':day,'origin':ORIGIN,'destination':DESTINATION,**found},
            'message':f"Verbindung gefunden: {day} · {ORIGIN} → {DESTINATION} · WB {found['trainNumber']} · 18:22–{found['arrival']} · Comfort 2+ · angezeigter Preis {price} €. KlimaTicket-Preis, Sitzplatz und Buchung nicht bestätigt."}


def prepare(page, day):
    day=date.fromisoformat(day).isoformat()
    if day < '2026-11-17': raise Blocked('Reisedatum vor dem ersten unreservierten Tag. Keine Suche.')
    dismiss_cookie_dialog(page)
    set_station(page,'Von',ORIGIN)
    set_station(page,'Nach',DESTINATION)
    if normalize_station(field(page,'Von').input_value()) not in {normalize_station(n) for n in STATION_LABELS[ORIGIN]} or normalize_station(field(page,'Nach').input_value()) not in {normalize_station(n) for n in STATION_LABELS[DESTINATION]}:
        raise Blocked('Bahnhofsauswahl hat sich geändert. Keine Suche.')
    confirm_date(page, day)
    # WESTbahn may load results automatically; do not click a search button if results exist.
    found=read_loaded_connection(page,day)
    if found is not None: return found
    # Legacy explicit-search forms remain supported; never click checkout.
    search=search_control(page)
    search.click(timeout=5000)
    found=read_loaded_connection(page,day)
    if found is not None: return found
    return {'status':'search_submitted','message':'Suchanfrage ausgelöst; Abfahrt 18:22, Verfügbarkeit, Klasse, Sitzplatz und Preis sind noch nicht verifiziert. Keine Buchung.'}

def inspect(page):
    if not official(page.url): raise Blocked('Browser außerhalb der erlaubten WESTbahn-Domain.')
    return {'status':'reachable','message':'Offizielle WESTbahn-Seite im Chromium geöffnet. Keine Anmeldung, Verfügbarkeit oder Buchung bestätigt.', 'originField': any(x.count()==1 and x.is_visible() for x in [page.get_by_label('Von',exact=True),page.get_by_placeholder('Von',exact=True)]),'destinationField':any(x.count()==1 and x.is_visible() for x in [page.get_by_label('Nach',exact=True),page.get_by_placeholder('Nach',exact=True)])}


ACCOUNT_URL = 'https://westbahn.de/ticketshop/dashboard/tickets?page=1&mode=valid'

def account_summary(page):
    # Only the authenticated valid-ticket view is considered. No action on tickets.
    parsed=urlsplit(page.url)
    if parsed.scheme!='https' or parsed.hostname not in ('westbahn.de','westbahn.at') or parsed.path.rstrip('/')!='/ticketshop/dashboard/tickets' or parse_qs(parsed.query).get('mode')!=['valid']:
        raise Blocked('WESTbahn-Konto nicht erreichbar oder Anmeldung abgelaufen.')
    try:
        page.get_by_text('Westbahn-Konto',exact=True).first.wait_for(timeout=15000)
        page.get_by_text('Gültige Tickets',exact=True).first.wait_for(timeout=5000)
    except PWTimeout:
        raise Blocked('Angemeldetes WESTbahn-Konto nicht eindeutig bestätigt.')
    # Find the smallest visible container for each observed Comfort ticket heading.
    # Return no ticket numbers, ticket codes, customer numbers or credentials.
    headings=page.get_by_text('Reservierung Comfort Class',exact=True)
    try:
        headings.first.wait_for(state='visible',timeout=6000)
    except PWTimeout:
        pass  # Empty or still loading: absence is never confirmed.
    def visible_cards():
        return headings.evaluate_all("""els => {
      const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
      return els.filter(visible).map(e=>{
        for(let n=e;n && n!==document.body;n=n.parentElement){
          const t=n.innerText||'';
          if(t.includes('Abfahrt') && t.includes('Ankunft') && t.includes('Sitzplatz') &&
             (t.match(/Reservierung Comfort Class/g)||[]).length===1) return t;
        }
        return '';
      });
    }""")
    # Collect virtualized/lazy-loaded tiles without clicking or modifying tickets.
    # Deduplicate full card text in memory only; never emit codes or identifiers.
    cards={}
    max_visible=0
    def collect():
        nonlocal max_visible
        snapshot=visible_cards()
        max_visible=max(max_visible,len(snapshot))
        for card in snapshot:
            if card: cards.setdefault(' '.join(card.split()),card)
    collect()
    first_count=len(cards)
    still=0
    scroll_passes=0
    for _ in range(16):
        moved=page.evaluate("""() => {
          const root=document.scrollingElement;
          const panels=[...document.querySelectorAll('main,section,div,ul,article')].filter(e=>{
            if(e===root || e.clientHeight<40 || e.scrollHeight<=e.clientHeight+2) return false;
            return /auto|scroll/.test(getComputedStyle(e).overflowY) &&
              (e.textContent||'').includes('Reservierung Comfort Class');
          });
          let moved=false;
          for(const e of [...new Set([root,...panels].filter(Boolean))]){
            const before=e.scrollTop;
            e.scrollTop=Math.min(e.scrollHeight,e.scrollTop+Math.max(80,Math.floor(e.clientHeight*.8)));
            if(e.scrollTop!==before) moved=true;
          }
          return moved;
        }""")
        page.wait_for_timeout(400)
        before=len(cards)
        collect()
        scroll_passes+=1
        still=still+1 if not moved and before==len(cards) else 0
        if still>=3: break
    rows=[]
    for card in cards.values():
        if not card: continue
        t=' '.join(card.split())
        if not re.search(r'\b18:22\b',t) or 'Wien Meidling' not in t or not re.search(r'\bWiener Neustadt\b',t): continue
        seat=re.search(r'\bSitzplatz\s+(\d{2,4}\s*[A-Z])\b',t)
        # The account tiles may omit the year. Never infer a complete date or
        # absence of a reservation from a partial page or a yearless label.
        label=re.search(r'\b(?:MO|DI|MI|DO|FR|SA|SO)\s+\d{1,2}\s+(?:JAN|JÄN|FEB|MÄR|APR|MAI|JUN|JUL|AUG|SEP|OKT|NOV|DEZ)(?:\s+\d{4})?\b',t,re.I)
        rows.append({'dateLabel':label.group(0) if label else None,'seat':seat.group(1).replace(' ','') if seat else None})
    return {'status':'account_verified','page':parse_qs(parsed.query).get('page',['1'])[0],'visibleComfortCards':max(max_visible,len(cards)),'matchingVisibleCards':rows,'scrollPasses':scroll_passes,'newCardsAfterScroll':len(cards)-first_count,
            'inventoryComplete':False,'message':f'WESTbahn-Konto bestätigt. {max(max_visible,len(cards))} erkannte Comfort-Reservierungen, davon {len(rows)} passende Pendlerfahrten; {len(cards)-first_count} neu beim Scrollen. Keine vollständige Bestandsprüfung; keine Buchung.'}



def account_audit(context, expected):
    # Compare both official storefronts independently. Never import or buy tickets.
    day=date.fromisoformat(expected)
    months=('JAN','FEB','MÄR','APR','MAI','JUN','JUL','AUG','SEP','OKT','NOV','DEZ')
    weekdays=('MO','DI','MI','DO','FR','SA','SO')
    month=months[day.month-1]
    label=re.compile(r'\b'+weekdays[day.weekday()]+r'\s+0?'+str(day.day)+r'\s+'+month+r'\b',re.I)
    numeric=re.compile(r'(?<!\d)0?'+str(day.day)+r'\.0?'+str(day.month)+r'\.(?:'+str(day.year)+r')?(?!\d)')
    reports=[]
    for domain in ('westbahn.de','westbahn.at'):
        for number in (1,2):
            page=context.new_page()
            try:
                target=f'https://{domain}/ticketshop/dashboard/tickets?page={number}&mode=valid'
                response=page.goto(target,wait_until='domcontentloaded',timeout=20000)
                http=response.status if response else None
                if http is None or http>=400:
                    reports.append({'domain':domain,'page':number,'status':'http_error','http':http})
                    break
                result=account_summary(page)
                # Detect a date even when the card's title/layout differs from our parser.
                body=page.locator('body').text_content(timeout=5000) or ''
                visible=page.locator('body').inner_text(timeout=5000)
                matches=[row for row in result['matchingVisibleCards'] if label.search(row.get('dateLabel') or '')]
                report={'domain':domain,'page':number,'status':'account_verified',
                        'finalDomain':urlsplit(page.url).hostname,'http':http,
                        'comfortCards':result['visibleComfortCards'],
                        'expectedMatches':matches,
                        'dateInVisibleText':bool(label.search(' '.join(visible.split())) or numeric.search(visible)),
                        'dateInDOM':bool(label.search(' '.join(body.split())) or numeric.search(body)),
                        'ticketImportControl':page.get_by_text(re.compile(r'Ticket hinzufügen|Ticket zum Westbahn-Konto hinzufügen',re.I)).count()>0}
                # Only expose numeric pagination destinations, not personal links.
                report['paginationPages']=page.evaluate("""() => [...new Set([...document.querySelectorAll('a[href]')].flatMap(a=>{
                  try {const u=new URL(a.href);const n=u.searchParams.get('page');
                  return u.origin===location.origin && u.pathname===location.pathname && /^\\d{1,3}$/.test(n||'')?[Number(n)]:[];}catch{return []}
                }))].sort((a,b)=>a-b)""")
                reports.append(report)
            except Blocked:
                reports.append({'domain':domain,'page':number,'status':'account_not_verified'})
                break
            except PWTimeout:
                reports.append({'domain':domain,'page':number,'status':'timeout'})
                break
            except Exception:
                reports.append({'domain':domain,'page':number,'status':'unavailable'})
                break
            finally:
                page.close()
    found=any(r.get('expectedMatches') for r in reports)
    marker=any(r.get('dateInVisibleText') or r.get('dateInDOM') for r in reports)
    return {'status':'account_audit','expectedDate':expected,'found':found,
            'diagnosis':'reservation_detected' if found else ('date_present_parser_needs_review' if marker else 'not_exposed_in_checked_web_views'),
            'reports':reports,'inventoryComplete':False,
            'message':'Nur lesender Abgleich der offiziellen Webkonten. Fehlende Treffer beweisen keine fehlende Reservierung.'}



def account_inventory(context, requested_page=None):
    """Read both storefronts; retain positive evidence even if one fails.
    Yearless labels and limited pagination must not authorize purchases."""
    reports=[]
    merged={}
    for domain in ('westbahn.at','westbahn.de'):
        pending=[requested_page] if requested_page is not None else [1,2]
        seen=set()
        while pending and len(seen)<10:
            number=pending.pop(0)
            if number in seen: continue
            seen.add(number)
            page=context.new_page()
            try:
                target=f'https://{domain}/ticketshop/dashboard/tickets?page={number}&mode=valid'
                response=page.goto(target,wait_until='domcontentloaded',timeout=20000)
                if response is None or response.status>=400:
                    reports.append({'domain':domain,'page':number,'status':'http_error','http':response.status if response else None})
                    break
                result=account_summary(page)
                final_domain=urlsplit(page.url).hostname
                final_page=parse_qs(urlsplit(page.url).query).get('page',['1'])[0]
                if final_domain!=domain or final_page!=str(number):
                    reports.append({'domain':domain,'page':number,'status':'unexpected_redirect'})
                    break
                reports.append({'domain':domain,'page':number,'status':'account_verified',
                                'comfortCards':result['visibleComfortCards'],
                                'matchingCards':len(result['matchingVisibleCards'])})
                for row in result['matchingVisibleCards']:
                    label=' '.join((row.get('dateLabel') or '').split()).upper()
                    seat=(row.get('seat') or '').replace(' ','').upper()
                    # Group equivalent visible date/seat labels, not unique ticket IDs.
                    key=(label,seat)
                    if key not in merged:
                        merged[key]={**row,'sources':[]}
                    if domain not in merged[key]['sources']:
                        merged[key]['sources'].append(domain)
                if requested_page is None:
                    links=page.evaluate("""() => [...new Set([...document.querySelectorAll('a[href]')].flatMap(a=>{
                      try {const u=new URL(a.href);const n=u.searchParams.get('page');
                        return u.origin===location.origin && u.pathname===location.pathname &&
                          /^\d{1,3}$/.test(n||'') && Number(n)>=1 && Number(n)<=100 &&
                          u.searchParams.get('mode')==='valid' ? [Number(n)] : [];
                      }catch{return []}
                    }))].sort((a,b)=>a-b)""")
                    pending.extend(n for n in links if n not in seen and n not in pending)
            except Blocked:
                reports.append({'domain':domain,'page':number,'status':'account_not_verified'})
                break
            except PWTimeout:
                reports.append({'domain':domain,'page':number,'status':'timeout'})
                break
            except Exception:
                reports.append({'domain':domain,'page':number,'status':'unavailable'})
                break
            finally:
                page.close()
    rows=list(merged.values())
    ok=any(r['status']=='account_verified' for r in reports)
    return {'status':'account_verified' if ok else 'blocked',
            'matchingVisibleCards':rows,'reports':reports,'inventoryComplete':False,
            'message':f'{len(rows)} unterschiedliche sichtbare Datum/Sitzplatz-Kombinationen auf beiden WESTbahn-Domains. Bestand nicht vollständig bestätigt; keine Buchung.'}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['login','probe','prepare','account','account-audit']);parser.add_argument('--date'); parser.add_argument('--page',type=int,default=None); args=parser.parse_args()
    if args.page is not None and not 1 <= args.page <= 100: raise Blocked('Ungültige Kontoseite.')
    root=Path(os.environ.get('WESTBAHN_BROWSER_PROFILE','./data/westbahn-browser')).resolve(); root.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(root,0o700)
    os.umask(0o077)
    with (root/'.agent.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Blocked('Browserprofil ist gerade in Benutzung.')
        with sync_playwright() as p:
            kwargs={'headless':args.mode!='login','timeout':20000,'accept_downloads':False}
            if os.environ.get('WESTBAHN_CHROMIUM_PATH'): kwargs['executable_path']=os.environ['WESTBAHN_CHROMIUM_PATH']
            context=p.chromium.launch_persistent_context(str(root/'chromium'),**kwargs)
            try:
                page=context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(5000)
                if args.mode!='login':
                    # Restrict automated top-level navigations; no external authentication flow.
                    def guard(route):
                        if route.request.is_navigation_request():
                            try: subframe=route.request.frame.parent_frame is not None
                            except Exception: subframe=False
                            if not allowed_navigation(route.request.url, subframe) and not (args.mode in ('account','account-audit') and urlsplit(route.request.url).scheme=='https' and urlsplit(route.request.url).hostname=='westbahn.de' and not urlsplit(route.request.url).username and not urlsplit(route.request.url).password): 
                                route.abort()
                                return
                        route.continue_()
                    context.route('**/*',guard)
                if args.mode=='account': return account_inventory(context,args.page)
                if args.mode=='account-audit':
                    if not args.date: raise Blocked('Reisedatum für Kontovergleich fehlt.')
                    return account_audit(context,args.date)
                if args.mode=='prepare' and not args.date: raise Blocked('Reisedatum fehlt.')
                target=date_url(args.date) if args.mode=='prepare' else URL
                page.goto(target,wait_until='domcontentloaded',timeout=25000)
                if args.mode=='login':
                    print('Melde dich im geöffneten WESTbahn-Browser an. Danach hier Enter drücken. Keine Zugangsdaten im Terminal eingeben.',file=sys.stderr,flush=True)
                    input(); return {'status':'profile_saved','message':'Browserprofil gespeichert; Anmeldung muss vor einer Buchung geprüft werden.'}
                if args.mode=='probe': return inspect(page)
                if not official(page.url): raise Blocked('Nicht erlaubte Browserseite.')
                if not args.date: raise Blocked('Reisedatum fehlt.')
                return prepare(page,args.date)
            finally: context.close()

if __name__=='__main__':
    try: print(json.dumps(main(),ensure_ascii=False))
    except Blocked as e: print(json.dumps({'status':'blocked','message':str(e)},ensure_ascii=False))
    except PWTimeout: print(json.dumps({'status':'blocked','message':'Zeitlimit beim WESTbahn-Suchformular. Bitte Suchfelder und Cookie-Dialog prüfen. Keine Buchung vorgenommen.'},ensure_ascii=False))
    except Exception: print(json.dumps({'status':'blocked','message':'Browser nicht verfügbar, Seite nicht erreichbar oder Ablauf nicht eindeutig. Keine Buchung vorgenommen.'},ensure_ascii=False))
