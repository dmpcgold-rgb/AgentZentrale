#!/usr/bin/env python3
"""Private WESTbahn browser. Read-only search; no checkout or payment actions."""
import argparse, fcntl, json, os, sys, re, shutil, tempfile
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit, parse_qs, urlencode
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from checkout_guard import audit_cart
from booking_evidence import assess_existing_ticket, extract_explicit_trip_date
from inventory_batch import validate_batch_dates, summarize_inventory_batch
from confirmation_evidence import reference_indicators, summarize_confirmation_candidates
from ticket_detail_view import inspect_existing_ticket_details

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
DEPARTURE_MARKER = re.compile(r'(?im)^[ \t]*Abfahrtszeit[,:]?[ \t]*(?=\n|(?:[01]\d|2[0-3]):[0-5]\d)')
TIME_LINE = r'(?:[01]\d|2[0-3]):[0-5]\d'

def parse_connection(text):
    lines = '\n'.join(' '.join(line.split()) for line in text.splitlines())
    blocks = DEPARTURE_MARKER.split(lines)[1:]
    matches = []
    for block in blocks:
        departure = re.match(r'^\s*(' + TIME_LINE + r')\b', block)
        if departure and departure.group(1) == '18:22':
            matches.append(block)
    if len(matches) != 1:
        raise Blocked(f'Abfahrt 18:22 nicht eindeutig ({len(matches)} Treffer). Keine Buchung.')
    block = matches[0]
    arrivals = re.findall(r'(?im)^Ankunftszeit[,:]?\s*(' + TIME_LINE + r')[ \t]*$', block)
    trains = re.findall(r'(?im)^(?:(?:WB|WESTbahn|Zug)\s*[: ]?\s*)?(\d{3,5})[ \t]*(?:\n[ \t]*|[ \t]+)fährt nach[ \t]+([^\n]+)$', block)
    # Only a price immediately attached to the 2+ class counts. Accept
    # currency before or after the amount and a whole-euro display.
    # A search price never establishes the final KlimaTicket checkout price.
    comfort = re.findall(r'(?im)^2\+[ \t]*(?:\|[ \t]*)?Comfort(?: Class)?[ \t]*(?:\n[ \t]*|[ \t]+)(€[ \t]*\d+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?[ \t]*€|kostenlos)[ \t]*$', block)
    class_labels=re.findall(r'(?im)^2\+[ \t]*(?:\|[ \t]*)?Comfort(?: Class)?(?=[ \t]*$|[ \t]+(?:€|\d|kostenlos))',block)
    if len(arrivals) != 1 or len(trains) != 1 or len(class_labels) != 1:
        # Narrow diagnostic: counts and public connection labels only.
        # Never include arbitrary body text, account details or ticket codes.
        hints=[]
        for line in block.splitlines():
            if re.fullmatch(r'(?i)(?:WB[ \t]*)?\d{3,5}|(?:Ankunftszeit[,:]?[ \t]*)?'+TIME_LINE+r'|2\+[ \t]*(?:\|[ \t]*)?Comfort(?: Class)?|(?:€[ \t]*\d+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?[ \t]*€|kostenlos)',line):
                hints.append(line)
        raise Blocked(f'Verbindung 18:22 unvollständig: Ankunft {len(arrivals)}, Zugnummer {len(trains)}, Comfort-Preis {len(comfort)}. Erkannte Zeilen: {" | ".join(hints[:16]) or "keine"}. Keine Buchung.')
    train, direction = trains[0]
    cents=None
    price_status='not_displayed' if not comfort else 'ambiguous'
    if len(comfort)==1:
        amount=comfort[0].replace('€','').strip().lower()
        if amount=='kostenlos':
            cents=0
        else:
            parts=amount.replace(',','.').split('.')
            cents=int(parts[0])*100+(int(parts[1]) if len(parts)==2 else 0)
        price_status='displayed'
    # Do not confuse a missing price with a free or available seat. Inspect
    # only the 2+ section, ending before the next class heading.
    section=re.split(r'(?im)^2\+[ \t]*(?:\|[ \t]*)?Comfort(?: Class)?',block,maxsplit=1)[1]
    section=re.split(r'(?im)^[ \t]*(?:1[ \t]*\|[ \t]*First|2[ \t]*\|[ \t]*Standard|Abfahrtszeit)\b',section,maxsplit=1)[0]
    unavailable=bool(re.search(r'(?i)\b(?:ausgebucht|nicht verfügbar|keine (?:freien )?Plätze|nicht reservierbar)\b',section))
    if unavailable:
        cents=None
        price_status='unavailable'
    return {'departure':'18:22','arrival':arrivals[0],'trainNumber':train,
            'direction':direction.strip(),'class':'2+','displayedPriceCents':cents,
            'currency':'EUR','priceStatus':price_status,
            'comfortAvailability':'unavailable' if unavailable else 'unverified',
            'priceVerifiedForKlimaTicket':False}


def read_loaded_connection(page, day):
    try:
        page.wait_for_function(r"""() => /Abfahrtszeit[,:]?\s*18:22\b/i.test(document.body.innerText)""",timeout=8000)
    except PWTimeout:
        pass
    text=page.locator('body').inner_text(timeout=5000)
    if not DEPARTURE_MARKER.search(text):
        return None
    # A rendered departure can arrive before its price/train details.
    # Retry incomplete results briefly, without clicking or booking anything.
    for attempt in range(5):
        try:
            found=parse_connection(text)
            if found['priceStatus']=='displayed' or found['priceStatus']=='unavailable' or attempt==4:
                break
            page.wait_for_timeout(700)
            text=page.locator('body').inner_text(timeout=5000)
        except Blocked:
            if attempt==4: raise
            page.wait_for_timeout(700)
            text=page.locator('body').inner_text(timeout=5000)
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
    found=apply_comfort_control_price(found,comfort_control_details(page,found))
    if found['displayedPriceCents'] is not None:
        price=f"{found['displayedPriceCents']/100:.2f}".replace('.',',')
        price_text=f'angezeigter Preis {price} €'
    elif found['priceStatus']=='unavailable':
        price_text='Comfort laut Anzeige nicht verfügbar'
    else:
        price_text='Comfort-Preis nicht eindeutig angezeigt'
    return {'status':'connection_found','connection':{'date':day,'origin':ORIGIN,'destination':DESTINATION,**found},
            'message':f"Verbindung gefunden: {day} · {ORIGIN} → {DESTINATION} · WB {found['trainNumber']} · 18:22–{found['arrival']} · Comfort 2+ · {price_text}. KlimaTicket-Preis, Sitzplatzverfügbarkeit und Buchung nicht bestätigt."}


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


def comfort_control_details(page, connection, return_button=False):
    # Inspect the actual rendered controls, not prices from the adjacent class.
    # No click, cart mutation or checkout. Output only public class information.
    script=r"""(connection) => {
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
      const classRe=/^2\+\s*\|?\s*Comfort(?: Class)?(?:\s|$)/i;
      const departureRe=/Abfahrtszeit[,:]?\s*(?:[01]\d|2[0-3]):[0-5]\d/g;
      const targetRe=/Abfahrtszeit[,:]?\s*18:22\b/;
      const labels=[...document.querySelectorAll('body *')].filter(e=>{
        if(!visible(e)||!classRe.test(norm(e.innerText)))return false;
        return ![...e.children].some(c=>visible(c)&&classRe.test(norm(c.innerText)));
      });
      const matches=[];
      const targets=[];
      for(const label of labels){
        let row=null;
        for(let e=label.parentElement;e && e!==document.body;e=e.parentElement){
          const t=e.innerText||'';
          const departures=t.match(departureRe)||[];
          if(departures.length>1)break;
          if(departures.length===1){
            if(targetRe.test(t)&&t.split(/\s+/).includes(connection.trainNumber)&&t.includes(connection.arrival))row=e;
            break;
          }
        }
        if(!row)continue;
        let control=label.closest('button,a[href],input,[role="button"],[role="link"],[tabindex]');
        if(control&&!row.contains(control))control=null;
        if(!control){
          for(let e=label;e&&e!==row;e=e.parentElement){
            const options=[...e.querySelectorAll('button,a[href],input,[role="button"],[role="link"]')].filter(visible);
            if(options.length===1){control=options[0];break;}
            if(options.length>1)break;
          }
        }
        let section=control||label;
        // A surrounding class cell often includes price/availability in siblings.
        for(let e=label.parentElement;e&&e!==row;e=e.parentElement){
          const t=norm(e.innerText);
          if(/(?:^|\s)(?:1\s*\|\s*First|2\s*\|\s*Standard|Abfahrtszeit)\b/i.test(t))break;
          if(classRe.test(t))section=e;
        }
        const values=[section.innerText,section.getAttribute('aria-label'),section.getAttribute('title'),
          control?.getAttribute('aria-label'),control?.getAttribute('title'),
          ...[...section.querySelectorAll('[title],[aria-label]')].slice(0,24).flatMap(e=>[e.getAttribute('title'),e.getAttribute('aria-label')])];
        const prices=[...new Set(values.flatMap(s=>(s||'').match(/(?:€\s*\d+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?\s*€)/g)||[]).map(norm))];
        const markers=[...new Set(values.flatMap(s=>(s||'').match(/ausgebucht|nicht verfügbar|nicht reservierbar|keine (?:freien )?Plätze|wenige Plätze|einige Plätze|viele Plätze|kostenlos|reservierbar/gi)||[]).map(norm))];
        const disabled=!!(control&&(control.matches(':disabled,[aria-disabled="true"]')||control.closest('[aria-disabled="true"],[inert]')));
        targets.push(control);
        matches.push({controlTag:control?.tagName.toLowerCase()||null,controlRole:control?.getAttribute('role')||null,
          disabled:control?disabled:null,visible:control?visible(control):null,
          pointerEvents:control?getComputedStyle(control).pointerEvents:null,prices,availabilityMarkers:markers});
      }
      if(connection.returnButton){
        const c=targets[0], m=matches[0];
        return matches.length===1 && c && c.tagName==="BUTTON" && m.visible && !m.disabled && m.pointerEvents!=="none" ? c : null;
      }
      return {targetClassLabels:matches.length,controls:matches};
    }"""
    args={"trainNumber":connection["trainNumber"],"arrival":connection.get("arrival","18:49"),"returnButton":return_button}
    if return_button:
        return page.evaluate_handle(script,args).as_element()
    return page.evaluate(script,args)



def apply_comfort_control_price(connection, detail):
    """Use a unique enabled Comfort control as a public price source only."""
    result=dict(connection)
    controls=detail.get('controls',[])
    if detail.get('targetClassLabels')!=1 or len(controls)!=1:
        return result
    control=controls[0]
    if not control.get('visible') or control.get('disabled') is not False or control.get('pointerEvents')=='none':
        return result
    if result.get('comfortAvailability')=='unavailable':
        return result
    if any(re.search(r'(?i)ausgebucht|nicht verfügbar|nicht reservierbar|keine (?:freien )?Plätze',m) for m in control.get('availabilityMarkers',[])):
        return result
    prices=set()
    for raw in control.get('prices',[]):
        amount=raw.replace('€','').strip().replace(',','.')
        if re.fullmatch(r'\d+(?:\.\d{2})?',amount):
            parts=amount.split('.')
            prices.add(int(parts[0])*100+(int(parts[1]) if len(parts)==2 else 0))
    if len(prices)!=1:
        return result
    cents=prices.pop()
    if result.get('displayedPriceCents') is not None and result['displayedPriceCents']!=cents:
        result.update(displayedPriceCents=None,priceStatus='ambiguous')
        return result
    result.update(displayedPriceCents=cents,priceStatus='displayed',priceSource='comfort_control',
                  priceVerifiedForKlimaTicket=False)
    return result


def inspect_comfort(page, day):
    result=prepare(page,day)
    if result.get("status")!="connection_found": return result
    detail=comfort_control_details(page,result["connection"])
    return {'status':'comfort_inspected','connection':result['connection'],'inspection':detail,
            'message':'Comfort-Bedienelemente nur gelesen. Kein Sitzplatz ausgewählt, keine Buchung.'}




def safe_request_summary(request):
    """Describe a blocked request without exposing its credentials or payload."""
    u=urlsplit(request.url)
    host=(u.hostname or '').lower()
    is_provider=host in ('westbahn.at','westbahn.de') or host.endswith(('.westbahn.at','.westbahn.de'))
    # Path components may contain ticket codes, account IDs or tokens.
    # Preserve only ordinary route labels; discard queries, fragments, headers,
    # bodies and any opaque/digit-containing or encoded segment.
    route_words=re.compile(r'^(?:api|rest|graphql|tickets?|ticketshop|reservation|reservations|reserve|booking|bookings|checkout|cart|basket|order|orders|seat|seats|seatmap|seat-map|seatselection|seat-selection|availability|train|trains|connection|connections|journey|journeys|trip|trips|coach|coaches|wagon|wagons|waggon|waggons|vehicle|vehicles|class|classes|comfort|search|offer|offers|price|prices|product|products|session|auth|account|dashboard|payment|payments|purchase|confirm|confirmation|add|remove|update|select|selection|layout|layouts|configuration|config|assets|static|css|js|images|fonts|public|data|shop|v[1-9])$',re.I)
    path='/'.join(s if route_words.fullmatch(s) else ':redacted' for s in u.path.split('/') if s)
    return {'method':request.method,'host':host if is_provider else 'other-origin',
            'path':'/'+path if is_provider else '/:redacted',
            'resourceType':request.resource_type,'hasQuery':bool(u.query)}


def offline_seat_preview(page, day, network_diagnostic=False):
    """Inspect a local-only transition; never transmit a class/seat click."""
    result=prepare(page,day)
    if result.get('status')!='connection_found':
        return {'status':'seat_preview_blocked',
                'blockReason':'connection_not_verified',
                'bookingAuthorized':False,'liveAvailabilityVerified':False}
    conn=result['connection']
    # Match the price-audit's repeated observations: the live DOM can update
    # the Comfort price asynchronously after results are first rendered.
    # Every observation is from this disposable browser, never another profile.
    original=conn
    price_samples=[]
    for attempt in range(4):
        details=comfort_control_details(page,original)
        fresh={**original,'displayedPriceCents':None,'priceSource':None,'priceStatus':'not_displayed'}
        conn=apply_comfort_control_price(fresh,details)
        price_samples.append(conn.get('displayedPriceCents'))
        zero_price=(original.get('displayedPriceCents') in (None,0)
                    and conn.get('displayedPriceCents')==0
                    and conn.get('priceSource')=='comfort_control'
                    and conn.get('priceStatus')=='displayed')
        if zero_price: break
        if attempt<3: page.wait_for_timeout(2000)
    if not network_diagnostic and not zero_price:
        return {'status':'seat_preview_blocked','blockReason':'zero_price_not_reconfirmed',
                'connectionPriceCents':original.get('displayedPriceCents'),
                'priceSamplesCents':price_samples,
                'targetClassLabels':details.get('targetClassLabels'),
                'controlCount':len(details.get('controls',[])),
                'bookingAuthorized':False,'liveAvailabilityVerified':False}
    controls=details.get('controls',[])
    if details.get('targetClassLabels')!=1 or len(controls)!=1 or controls[0].get('controlTag')!='button' or controls[0].get('disabled') is not False:
        return {'status':'seat_preview_blocked','blockReason':'comfort_control_ambiguous',
                'bookingAuthorized':False,'liveAvailabilityVerified':False}
    # Network diagnostic may examine a nonzero/unknown price ONLY offline.
    # It must not be reused as a live availability or booking authorization.
    # The caller uses a disposable context with service workers and websockets
    # blocked. Set the entire context offline BEFORE the sole preview click.
    # No request generated by this click is allowed to reach the provider.
    blocked_requests=[]
    def deny(route):
        if len(blocked_requests)<100: blocked_requests.append(safe_request_summary(route.request))
        route.abort()
    page.context.route('**/*',deny)
    page.context.set_offline(True)
    # Use the very same DOM resolver as price inspection. Labels can be siblings
    # of a button rather than text inside it. Never select by a second heuristic.
    button=comfort_control_details(page,conn,return_button=True)
    if button is None:
        return {'status':'seat_preview_blocked','blockReason':'comfort_click_target_ambiguous',
                'bookingAuthorized':False,'liveAvailabilityVerified':False}
    try:
        button.click(timeout=5000,no_wait_after=True)
        page.wait_for_timeout(2500)
    except PWTimeout:
        return {'status':'seat_preview_blocked','blockReason':'offline_click_timeout',
                'bookingAuthorized':False,'liveAvailabilityVerified':False}
    observations=page.evaluate(r"""() => {
      const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const seats=[];
      for(const e of document.querySelectorAll('button,[role="button"],[role="option"],[data-seat],[data-seat-number]')){
        if(!visible(e))continue;
        const labels=[e.innerText,e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('data-seat'),e.getAttribute('data-seat-number')].map(norm);
        const codes=[...new Set(labels.flatMap(t=>{const m=t.match(/^(?:Sitzplatz\s*)?(\d{2,4})\s*([A-D])$/i);return m?[m[1]+m[2].toUpperCase()]:[]}))];
        if(codes.length===1)seats.push({seat:codes[0],disabled:e.matches(':disabled,[aria-disabled="true"]')||!!e.closest('[aria-disabled="true"],[inert]')});
      }
      const t=document.body.innerText||'';
      return {seatControls:seats.slice(0,300),
        seatMapLabel:/Sitzplatz(?:auswahl| auswählen)|Wagen(?:auswahl| auswählen)|Sitzplan/i.test(t)};
    }""")
    preferences=['233A','233D','191D','182A','193A','193D']
    return {'status':'seat_network_diagnostic' if network_diagnostic else 'seat_preview_offline','connection':conn,'inspection':observations,
            'zeroPriceObserved':zero_price,'bookingAuthorized':False,
            'preferredControls':[s for s in observations['seatControls'] if s['seat'] in preferences],
            'blockedRequestCount':len(blocked_requests),'blockedRequests':blocked_requests,'liveAvailabilityVerified':False,
            'message':'Isolierte Offline-Vorschau; keine Anfrage aus dem Comfort-Klick an WESTbahn übertragen. Sichtbare Plätze sind keine bestätigte Live-Verfügbarkeit.'}


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
        full_date=extract_explicit_trip_date(t)
        references=reference_indicators(t)
        rows.append({'dateLabel':label.group(0) if label else None,
                     'seat':seat.group(1).replace(' ','') if seat else None,
                     'fullDate':full_date,
                     **references})
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



def account_inventory(context, requested_page=None, max_pages=10):
    """Read both storefronts; retain positive evidence even if one fails.
    Yearless labels and limited pagination must not authorize purchases."""
    reports=[]
    merged={}
    for domain in ('westbahn.at','westbahn.de'):
        pending=[requested_page] if requested_page is not None else [1,2]
        seen=set()
        while pending and len(seen)<max_pages:
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
                    # Keep stronger positive evidence seen on either official domain.
                    merged[key]['bookingReference']=merged[key].get('bookingReference') is True or row.get('bookingReference') is True
                    merged[key]['ticketReference']=merged[key].get('ticketReference') is True or row.get('ticketReference') is True
                    merged[key]['ticketCode']=merged[key].get('ticketCode') is True or row.get('ticketCode') is True
                    if merged[key].get('fullDate') is None and row.get('fullDate'):
                        merged[key]['fullDate']=row['fullDate']
                    elif merged[key].get('fullDate') and row.get('fullDate') and merged[key]['fullDate']!=row['fullDate']:
                        # Conflicting journey years must not be silently resolved.
                        merged[key]['fullDate']='conflicting'
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



def copy_preview_profile(source, destination):
    """Clone a closed Chromium profile without startup tabs, caches or locks."""
    if not source.is_dir():
        raise Blocked('Gespeichertes Browserprofil fehlt.')
    omit={'SingletonLock','SingletonCookie','SingletonSocket','LOCK','lockfile',
          'Cache','Code Cache','GPUCache','DawnGraphiteCache','DawnWebGPUCache',
          'Crashpad','Sessions','Current Session','Current Tabs','Last Session','Last Tabs'}
    def ignore(path,names):
        return [n for n in names if n in omit or (Path(path)/n).is_symlink()]
    shutil.copytree(source,destination,ignore=ignore)

def run_seat_preview(p, root, kwargs, day, network_diagnostic=False):
    # Match price-audit: first verify/refresh the login in the original
    # persistent browser, then close it BEFORE cloning the saved profile.
    # Never auto-login in a disposable copy or expose credentials in results.
    # The caller holds the exclusive profile lock for both phases.
    original=p.chromium.launch_persistent_context(str(root/'chromium'),**kwargs)
    try:
        main_page=original.pages[0] if original.pages else original.new_page()
        main_page.set_default_timeout(5000)
        session=ensure_austrian_session(main_page,root)
        if session.get('status')!='account_verified':
            return {'status':'seat_preview_blocked',
                    'blockReason':'original_account_unverified',
                    'accountCheckStatus':session.get('status','account_unverified'),
                    'accountVerifiedBeforeSearch':False,
                    'bookingAuthorized':False,'liveAvailabilityVerified':False}
    finally:
        original.close()
    # Preserve IndexedDB, cookies and local settings in the temporary copy.
    # The disposable copy can only verify its already-established session.
    with tempfile.TemporaryDirectory(prefix='.seat-preview-',dir=root) as tmp:
        profile=Path(tmp)/'chromium'
        copy_preview_profile(root/'chromium',profile)
        preview=p.chromium.launch_persistent_context(str(profile),**kwargs,
                    service_workers='block',args=['--no-first-run','--disable-background-networking'])
        try:
            def guard(route):
                if route.request.is_navigation_request():
                    try: subframe=route.request.frame.parent_frame is not None
                    except Exception: subframe=False
                    # Match the working restricted price-audit: WESTbahn's
                    # own login redirect may use a different official host.
                    # No other top-level navigation is allowed.
                    if not allowed_navigation(route.request.url,subframe) and not trusted_login_url(route.request.url):
                        route.abort()
                        return
                route.continue_()
            preview.route('**/*',guard)
            preview.route_web_socket('**/*',lambda ws: ws.close())
            q=preview.pages[0] if preview.pages else preview.new_page()
            q.set_default_timeout(5000)
            # Unlike the old preview, verify the Austrian account in this
            # exact cloned browser BEFORE opening the fare search. Do not
            # reuse credentials or an auth result from the main profile.
            session=verify_austrian_session(q)
            if session.get('status')!='account_verified':
                return {'status':'seat_preview_blocked',
                        'blockReason':'preview_account_unverified',
                        'accountCheckStatus':session.get('status','account_unverified'),
                        'accountVerifiedBeforeSearch':False,
                        'bookingAuthorized':False,'liveAvailabilityVerified':False}
            q.goto(date_url(day),wait_until='domcontentloaded',timeout=25000)
            result=offline_seat_preview(q,day,network_diagnostic=network_diagnostic)
            result['accountVerifiedBeforeSearch']=True
            return result
        finally: preview.close()



def price_audit_view(context, day, root=None):
    """Compare public Comfort prices only AFTER verifying this exact browser session.

    The normal persistent profile may use the already configured, rate-limited
    WESTbahn login. Disposable copies only check their own session and never
    receive credentials or initiate login. This remains a read-only diagnostic.
    """
    def guard(route):
        if route.request.is_navigation_request():
            try: subframe=route.request.frame.parent_frame is not None
            except Exception: subframe=False
            if not allowed_navigation(route.request.url,subframe) and not trusted_login_url(route.request.url):
                route.abort()
                return
        route.continue_()
    context.route('**/*',guard)
    q=context.pages[0] if context.pages else context.new_page()
    q.set_default_timeout(5000)
    report={'accountVerified':False,'accountVerifiedBeforeSearch':False,
            'priceSamplesCents':[],'status':'account_unverified_before_search'}
    try:
        session=(ensure_austrian_session(q,root) if root is not None
                 else verify_austrian_session(q))
        if session.get('status')!='account_verified':
            return report
        report['accountVerifiedBeforeSearch']=True
    except Exception:
        return report
    try:
        q.goto(date_url(day),wait_until='domcontentloaded',timeout=25000)
        result=prepare(q,day)
        if result.get('status')=='connection_found':
            conn=result['connection']
            for i in range(4):
                detail=comfort_control_details(q,conn)
                fresh={**conn,'displayedPriceCents':None,'priceSource':None,
                       'priceStatus':'not_displayed'}
                observed=apply_comfort_control_price(fresh,detail)
                report['priceSamplesCents'].append(observed['displayedPriceCents'])
                if i<3: q.wait_for_timeout(2000)
            report['connection']={k:conn[k] for k in ('date','trainNumber','departure','arrival','class')}
            report['status']='price_observed'
        else: report['status']=result.get('status','unknown')
    except Blocked:
        report['status']='blocked'
    except PWTimeout:
        report['status']='timeout'
    except Exception:
        report['status']='unavailable'
    # Independently re-check the same session after search; never expose
    # provider pages, identifiers, credentials, cookies or ticket cards.
    try:
        report['accountVerified']=(verify_austrian_session(q).get('status')=='account_verified')
    except Exception:
        pass
    return report

def classify_price_audit(normal, clone, restricted):
    def stable_zero(r):
        samples=r.get('priceSamplesCents',[])
        return bool(samples) and samples[-1]==0
    if normal.get('accountVerifiedBeforeSearch') is not True:
        return 'normal_session_unverified'
    if not stable_zero(normal):
        return 'normal_browser_zero_not_confirmed'
    if clone.get('accountVerifiedBeforeSearch') is not True:
        return 'cloned_session_unverified'
    if not stable_zero(clone):
        return 'profile_copy_price_differs'
    if restricted.get('accountVerifiedBeforeSearch') is not True:
        return 'restricted_session_unverified'
    if not stable_zero(restricted):
        return 'restricted_context_price_differs'
    return 'isolated_zero_observed'

def run_price_audit(p, root, kwargs, day):
    day=date.fromisoformat(day).isoformat()
    if day<'2026-11-17': raise Blocked('Reisedatum vor dem ersten unreservierten Tag.')
    # All three runs are read-only searches, with no class or seat clicks.
    # Run with identical profile state copied after closing the original browser.
    normal=p.chromium.launch_persistent_context(str(root/'chromium'),**kwargs)
    try: normal_report=price_audit_view(normal,day,root=root)
    finally: normal.close()
    reports=[]
    for restricted in (False,True):
        with tempfile.TemporaryDirectory(prefix='.price-audit-',dir=root) as tmp:
            profile=Path(tmp)/'chromium'
            copy_preview_profile(root/'chromium',profile)
            extra={'service_workers':'block','args':['--no-first-run','--disable-background-networking']} if restricted else {}
            ctx=p.chromium.launch_persistent_context(str(profile),**kwargs,**extra)
            try:
                if restricted: ctx.route_web_socket('**/*',lambda ws: ws.close())
                reports.append(price_audit_view(ctx,day))
            finally: ctx.close()
    return {'status':'price_audit','date':day,'normal':normal_report,'cloned':reports[0],
            'restricted':reports[1],'diagnosis':classify_price_audit(normal_report,*reports),
            'message':'Nur Preis- und Anmeldeprüfung. Keine Comfort-Auswahl, Sitzplatzauswahl oder Buchung.'}



AUSTRIAN_ACCOUNT_URL='https://westbahn.at/ticketshop/dashboard/tickets?page=1&mode=valid'

def verify_austrian_session(page):
    """Verify the actual authenticated account in the current browser session."""
    try:
        response=page.goto(AUSTRIAN_ACCOUNT_URL,wait_until='domcontentloaded',timeout=25000)
        u=urlsplit(page.url)
        if response is None or response.status>=400:
            return {'status':'account_unverified','message':'WESTbahn-Konto momentan nicht erreichbar. Keine Buchung.'}
        if u.scheme!='https' or u.hostname!='westbahn.at' or u.path.rstrip('/')!='/ticketshop/dashboard/tickets':
            return {'status':'login_required','message':'Österreichisches WESTbahn-Konto nicht geöffnet. Bitte im privaten Browser anmelden. Keine Buchung.'}
        page.get_by_text('Westbahn-Konto',exact=True).first.wait_for(state='visible',timeout=15000)
        page.get_by_text('Gültige Tickets',exact=True).first.wait_for(state='visible',timeout=5000)
        u=urlsplit(page.url)
        if u.scheme=='https' and u.hostname=='westbahn.at' and u.path.rstrip('/')=='/ticketshop/dashboard/tickets' and parse_qs(u.query).get('mode')==['valid']:
            return {'status':'account_verified','message':'Österreichisches WESTbahn-Konto in dieser Browsersitzung bestätigt.'}
    except Exception:
        pass
    return {'status':'account_unverified','message':'Anmeldung auf westbahn.at nicht eindeutig bestätigt. Keine Buchung.'}


LOGIN_URL='https://westbahn.at/anmelden/'

def trusted_login_url(url):
    u=urlsplit(url)
    return u.scheme=='https' and u.hostname in ('westbahn.at','www.westbahn.at','westbahn.de','www.westbahn.de') and not u.username and not u.password and u.port in (None,443)

def credential_path(root):
    return root/'westbahn-login.json'

def configure_login(root):
    import getpass
    if not sys.stdin.isatty(): raise Blocked('Zugangsdaten nur interaktiv am privaten SSH-Terminal hinterlegen.')
    email=input('WESTbahn E-Mail: ').strip()
    password=getpass.getpass('WESTbahn Passwort (unsichtbar): ')
    if not email or '@' not in email or not password: raise Blocked('E-Mail oder Passwort fehlt.')
    fd,name=tempfile.mkstemp(prefix='.login-',dir=root)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump({'email':email,'password':password},f)
            f.flush(); os.fsync(f.fileno())
        os.chmod(name,0o600)
        os.replace(name,credential_path(root))
        (root/'.login-attempt').unlink(missing_ok=True)
    finally:
        if os.path.exists(name): os.unlink(name)
    return {'status':'credentials_saved','message':'WESTbahn-Zugangsdaten privat auf dem Server gespeichert. Nicht in GitHub oder Browserprofilkopien.'}

def load_login(root):
    path=credential_path(root)
    if not path.exists(): return None
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid!=os.getuid():
        raise Blocked('Unsichere Berechtigungen der WESTbahn-Zugangsdaten.')
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or not isinstance(data.get('email'),str) or not isinstance(data.get('password'),str) or not data['email'] or not data['password']:
        raise Blocked('WESTbahn-Zugangsdaten fehlen oder sind ungültig.')
    return data

def login_fields(page):
    """Require a single visible password form and a single email and login button."""
    def visible(loc):
        return [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
    passwords=visible(page.locator('input[type="password"]'))
    if len(passwords)!=1: return None
    password=passwords[0]
    form=password.locator('xpath=ancestor::form[1]')
    scope=form if form.count()==1 else page
    if form.count()==1:
        action=form.evaluate('(f) => f.action')
        if not trusted_login_url(action): return None
    emails=visible(scope.locator('input[type="email"],input[autocomplete="username"],input[name="email"],input[name="username"],input[autocomplete="email"]'))
    buttons=visible(scope.get_by_role('button',name=re.compile(r'^\s*(Anmelden|Einloggen|Login|Log in|Sign in)\s*$',re.I)))
    if len(emails)!=1 or len(buttons)!=1: return None
    if not buttons[0].is_enabled() and not emails[0].is_editable(): return None
    return emails[0],password,buttons[0]

def ensure_austrian_session(page, root=None):
    session=verify_austrian_session(page)
    if session['status']=='account_verified' or root is None: return session
    data=load_login(root)
    if not data:
        return {'status':'login_required','message':'Automatische Anmeldung noch nicht eingerichtet. credentials-set ausführen. Keine Buchung.'}
    import time
    attempt=root/'.login-attempt'
    if attempt.exists() and time.time()-attempt.stat().st_mtime<600:
        return {'status':'login_required','message':'Erneute automatische Anmeldung vorübergehend gesperrt (10 Minuten). Konto manuell prüfen. Keine Buchung.'}
    try:
        response=page.goto(LOGIN_URL,wait_until='domcontentloaded',timeout=25000)
        if response is None or response.status>=400 or not trusted_login_url(page.url):
            return {'status':'account_unverified','message':'Offizielle WESTbahn-Anmeldeseite nicht erreichbar. Keine Buchung.'}
        # Do not submit anything if the account is already authenticated.
        if '/ticketshop/dashboard/' in urlsplit(page.url).path:
            return verify_austrian_session(page)
        for _ in range(8):
            fields=login_fields(page)
            if fields: break
            page.wait_for_timeout(750)
        else:
            return {'status':'login_required','message':'Loginformular nicht eindeutig erkannt. Manuelle Anmeldung erforderlich. Keine Buchung.'}
        email,password,button=fields
        # A separate challenge must never be solved or bypassed automatically.
        if page.locator('iframe[src*="captcha"],iframe[src*="recaptcha"],iframe[src*="turnstile"]').count() or page.locator('input[autocomplete="one-time-code"]').count():
            return {'status':'login_required','message':'Zusätzliche Sicherheitsprüfung erforderlich. Manuell anmelden. Keine Buchung.'}
        if not trusted_login_url(page.url): raise Blocked('Anmeldeseite gewechselt.')
        email.fill(data['email'])
        password.fill(data['password'])
        if not trusted_login_url(page.url): raise Blocked('Anmeldeseite gewechselt.')
        if not button.is_enabled(): return {'status':'login_required','message':'Anmeldebutton nicht aktiv. Keine Buchung.'}
        # One attempt per cooldown; do not retry a failed password repeatedly.
        attempt.touch(mode=0o600)
        button.click(timeout=8000)
        try:
            page.wait_for_function("""() => location.pathname.includes('/ticketshop/dashboard/') || document.body.innerText.includes('Westbahn-Konto')""",timeout=15000)
        except PWTimeout:
            pass
        verified=verify_austrian_session(page)
        if verified['status']=='account_verified':
            attempt.unlink(missing_ok=True)
            verified['autoLogin']=True
            return verified
    except Exception:
        pass
    return {'status':'login_required','message':'Automatische Anmeldung nicht bestätigt. Passwort oder zusätzliche Sicherheitsprüfung manuell prüfen. Keine Buchung.'}


def authenticated_prepare(page, day, inspect_only=False, root=None):
    day=date.fromisoformat(day).isoformat()
    if day<'2026-11-17': raise Blocked('Reisedatum vor dem ersten unreservierten Tag.')
    session=ensure_austrian_session(page,root)
    if session['status']!='account_verified': return session
    page.goto(date_url(day),wait_until='domcontentloaded',timeout=25000)
    if not official(page.url): raise Blocked('Nicht erlaubte Browserseite.')
    result=inspect_comfort(page,day) if inspect_only else prepare(page,day)
    result['accountVerifiedBeforeSearch']=True
    result['bookingAuthorized']=False
    return result


# Verified against the visible WESTbahn seat plan. These are preferred seats,
# not a guarantee of availability or a rule that other train layouts are identical.
PRIMARY_SEATS=('233A','233D')
PRIMARY_COACH='11'

def seat_modal_state(page, target=None):
    """Inspect a unique seat-picker modal, or return a unique safe control handle."""
    script=r"""(target) => {
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const vis=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
      const text=e=>norm(e.innerText||e.textContent);
      const titles=[...document.querySelectorAll('body *')].filter(e=>vis(e)&&text(e)==='Sitzplatzreservierung'&&![...e.children].some(c=>vis(c)&&text(c)==='Sitzplatzreservierung'));
      const modals=new Set();
      for(const t of titles){
        for(let e=t.parentElement;e&&e!==document.body;e=e.parentElement){
          const buttons=[...e.querySelectorAll('button,[role="button"]')].filter(vis);
          if(buttons.some(b=>text(b)==='Abbrechen')&&buttons.some(b=>text(b)==='Bestätigen')){modals.add(e);break;}
        }
      }
      const smallest=[...modals].filter(e=>![...modals].some(other=>other!==e&&e.contains(other)));
      if(smallest.length!==1)return target?null:{modalFound:false,controls:[]};
      const modal=smallest[0];
      if(target&&target.kind==='confirm'){
        const buttons=[...modal.querySelectorAll('button,[role="button"]')].filter(e=>vis(e)&&text(e)==='Bestätigen'&&!e.matches(':disabled,[aria-disabled="true"]')&&getComputedStyle(e).pointerEvents!=='none');
        return buttons.length===1?buttons[0]:null;
      }
      // The selected-seat summary precedes the actual seat map. Never use an
      // arbitrary seat label in the map as evidence of the selected seat.
      const beforeMap=(modal.innerText||modal.textContent||'').split(/Legende|2\+\s*\|\s*Comfort|2\+\s*Comfort/i)[0];
      const summary=beforeMap.match(/Wagen\s+Platz\s+(\d{1,2})\s+(?:[♿\s\uFE0F]*)?(\d{2,4})\s*([A-D])\b/i)||beforeMap.match(/Wagen\s+(\d{1,2})\s+Platz\s+(?:[♿\s\uFE0F]*)?(\d{2,4})\s*([A-D])\b/i);
      const selected=summary?{coach:summary[1],seat:summary[2]+summary[3].toUpperCase()}:null;
      const controls=[];
      const elements=[];
      const activeCoaches=[];
      // The live map may render its class label as SVG text or accessibility
      // metadata, which innerText alone misses.
      const isComfort=s=>/2\s*\+\s*[\s|·:–—-]*Comfort/i.test(norm(s));
      const classLabel=[...modal.querySelectorAll('*')].some(e=>vis(e)&&[e.getAttribute('aria-label'),e.getAttribute('title'),e.textContent].some(v=>v&&isComfort(v)&&norm(v).length<70));
      const comfortMap=isComfort(modal.innerText)||isComfort(modal.textContent)||classLabel;
      // For the four explicitly approved seats only, a scoped zero-price
      // Comfort summary can supplement a missing coach-class label.
      const headings=[...document.querySelectorAll('body *')].filter(e=>vis(e)&&text(e)==='Meine Auswahl'&&![...e.children].some(c=>vis(c)&&text(c)==='Meine Auswahl'));
      const summaries=new Set();
      for(const h of headings){
        for(let e=h.parentElement;e&&e!==document.body;e=e.parentElement){
          const v=norm(e.innerText||e.textContent);
          if(/Reservierung\s+Comfort\s+Class/i.test(v)&&/\b1009\b/.test(v)&&/18:22/.test(v)&&/Wien\s+Meidling/i.test(v)&&/Wiener\s+Neustadt/i.test(v)&&/(?:€\s*0[,.]00|0[,.]00\s*€)/.test(v)&&v.length<1500){summaries.add(e);break;}
        }
      }
      const detailComfort=summaries.size===1;
      const known=new Set(['233A','233D','191D','182A']);
      for(const e of modal.querySelectorAll('button,[role="button"],[role="option"],[data-seat],[data-seat-number]')){
        if(!vis(e))continue;
        const raw=[text(e),e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('data-seat'),e.getAttribute('data-seat-number')].map(norm);
        const code=raw.map(v=>v.match(/^(?:Sitzplatz\s*)?(\d{2,4})\s*([A-D])(?:\s*(?:[,;:\-–]\s*)?(?:frei|verfügbar|ausgewählt|nicht verfügbar|belegt))?$/i)).find(Boolean);
        const coach=raw.map(v=>v.match(/^(?:Wagen\s*)?(\d{1,2})$/i)).find(Boolean);
        if(!code&&!coach)continue;
        const state=[...raw,e.getAttribute('class')||'',e.getAttribute('data-status')||'',e.getAttribute('aria-selected')||''].join(' ');
        const disabled=e.matches(':disabled,[aria-disabled="true"]')||!!e.closest('[aria-disabled="true"],[inert]')||getComputedStyle(e).pointerEvents==='none';
        const unavailable=/nicht verfügbar|nicht reservierbar|belegt|ausgebucht|unavailable|occupied|blocked|disabled/i.test(state);
        const free=!disabled&&!unavailable&&/(?:\bfrei\b|\bverfügbar\b|\bavailable\b|\bfree\b)/i.test(state);
        const groupNode=code?e.closest('[data-seat-group],[data-table-id]'):null;
        const group=groupNode?(groupNode.getAttribute('data-seat-group')||groupNode.getAttribute('data-table-id')):null;
        const layout=groupNode?(groupNode.getAttribute('data-seat-layout')||groupNode.getAttribute('data-layout')||'').toLowerCase():'';
        const fourSeat=/four|4er|vierer|4-seat/.test(layout);
        if(coach && !code){
          const active=e.matches('[aria-selected="true"],[aria-pressed="true"],[aria-current="true"],[data-active="true"]')||/(?:^|[\s_-])(active|selected)(?:$|[\s_-])/i.test(e.getAttribute('class')||'');
          if(active)activeCoaches.push(coach[1]);
        }
        const seatId=code?code[1]+code[2].toUpperCase():null;
        // WESTbahn's enabled seat controls do not necessarily say "frei".
        // Only use this signal for user-approved seats, not unknown layouts.
        const selectableKnown=!!code&&known.has(seatId)&&!disabled&&!unavailable&&!fourSeat&&e.matches('button,[role="button"],[role="option"]')&&e.getAttribute('aria-disabled')!=='true';
        controls.push({kind:code?'seat':'coach',value:code?seatId:coach[1],disabled,unavailable,free,selectableKnown,
          ...(code?{group:group?String(group).slice(0,60):null,layout,fourSeat}:{})});
        elements.push(e);
      }
      if(target){
        const matches=controls.map((c,i)=>({c,i})).filter(({c})=>c.kind===target.kind&&c.value===target.value&&!c.disabled&&!c.unavailable&&(c.kind!=='seat'||c.free||(target.allowKnown===true&&c.selectableKnown)));
        return matches.length===1?elements[matches[0].i]:null;
      }
      const active=[...new Set(activeCoaches)];
      // WESTbahn's selected coach can also be represented by a blue
      // control without an aria state. Require unique visual evidence.
      const blue=[];
      if(!active.length){
        for(let i=0;i<controls.length;i++){
          if(controls[i].kind!=='coach')continue;
          const rgb=getComputedStyle(elements[i]).backgroundColor.match(/\d+/g);
          if(rgb&&+rgb[2]>+rgb[0]+35&&+rgb[1]>+rgb[0]+20&&+rgb[0]<120)blue.push(controls[i].value);
        }
      }
      const activeCoach=active.length===1?active[0]:!active.length&&new Set(blue).size===1?blue[0]:null;
      return {modalFound:true,selected,controls,activeCoach,comfortMap,detailComfort};
    }"""
    if target is not None:
        return page.evaluate_handle(script,target).as_element()
    return page.evaluate(script,None)


def read_review_command(page):
    """Keep Playwright processing browser events while waiting for SSH input."""
    import queue, threading
    commands=queue.Queue(maxsize=1)
    def read():
        try: commands.put(input().strip().lower())
        except (EOFError, KeyboardInterrupt): commands.put('q')
    threading.Thread(target=read,daemon=True).start()
    context=page.context
    while True:
        try: return commands.get_nowait()
        except queue.Empty: pass
        # Sync Playwright only dispatches events while its API is running.
        # A blocking input() leaves page.url and new-tab events stale.
        active=[p for p in context.pages if not p.is_closed()]
        if not active: return 'q'
        try: active[0].wait_for_timeout(100)
        except Exception:
            if not any(not p.is_closed() for p in context.pages): return 'q'

def is_review_detail_url(url, day=None):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname!='westbahn.at' or u.username or u.password or u.port not in (None,443) or u.path.rstrip('/')!='/reservierung/sitzplatz-upgrade/details':
        return False
    if day is None: return True
    q=parse_qs(u.query)
    return q.get('do')==[day] and q.get('sf')==['wien-meidling'] and q.get('st')==['wiener-neustadt']

def find_open_review_page(original, day):
    """Resolve the actual live tab, not the cached URL of the initial page."""
    matches=[]
    reports=[]
    for p in original.context.pages:
        if p.is_closed(): continue
        try:
            url=p.evaluate('window.location.href')
            u=urlsplit(url)
            detail=is_review_detail_url(url)
            route_matches=is_review_detail_url(url,day)
            report={'pageKind':'detail' if detail else 'search' if u.hostname=='westbahn.at' and u.path.rstrip('/')=='/reservierung/sitzplatz-upgrade' else 'other',
                    'routeMatches':route_matches,'modalFound':False}
            if route_matches:
                state=seat_modal_state(p)
                report['modalFound']=bool(state.get('modalFound'))
                if report['modalFound']: matches.append(p)
            reports.append(report)
        except Exception:
            reports.append({'pageKind':'unavailable','routeMatches':False,'modalFound':False})
    return (matches[0] if len(matches)==1 else None,
            {'openPages':reports,'matchingSeatDialogs':len(matches)})


# User-approved alternatives observed in the previous reservations.
PREFERRED_SEAT_GROUPS=(('11',('233A','233D')),('8',('191D',)),('7',('182A',)))

def ranked_layout_seats(state):
    """Only explicit, complete two-seat groups are eligible for generic fallback."""
    groups={}
    for c in state.get('controls',[]):
        if c.get('kind')=='seat' and c.get('group'):
            groups.setdefault(c['group'],[]).append(c)
    result=[]
    for group in groups.values():
        # Include unavailable seats in the count; a four-seat table with two
        # occupied places must never be mistaken for a two-seat group.
        if len(group)!=2 or len({c['value'] for c in group})!=2: continue
        layouts={c.get('layout') for c in group}
        if layouts=={'single-facing-table'}: rank=0
        elif layouts=={'single-offset-facing'}: rank=1
        else: continue
        if any(c.get('fourSeat') for c in group): continue
        for c in group:
            if c.get('free') and not c.get('disabled') and not c.get('unavailable'):
                result.append((rank,c['value']))
    return sorted(result)

def select_primary_seat_in_open_modal(page):
    """Search preferred and explicitly verified two-seat layouts. Never confirm or buy."""
    if not is_review_detail_url(page.evaluate('window.location.href')):
        return {'status':'seat_selection_blocked','bookingAuthorized':False,'message':'Keine eindeutige WESTbahn-Reservierungsdetailseite.'}
    state=seat_modal_state(page)
    if not state.get('modalFound'):
        return {'status':'seat_selection_blocked','bookingAuthorized':False,'inspection':state,'message':'Sitzplan nicht eindeutig geöffnet.'}
    reports=[]
    def blocked(message):
        return {'status':'seat_selection_blocked','bookingAuthorized':False,'inspection':seat_modal_state(page),'coachReports':reports,'message':message}
    def open_coach(coach):
        current=seat_modal_state(page)
        # The selected-seat summary may still refer to a different coach.
        control=seat_modal_state(page,{'kind':'coach','value':coach})
        if control is None:
            return None
        control.click(timeout=5000)
        for _ in range(12):
            page.wait_for_timeout(250)
            current=seat_modal_state(page)
            if current.get('activeCoach')==coach and (current.get('comfortMap') or (coach in ('11','8','7') and current.get('detailComfort'))):
                return current
        # No arbitrary fallback on a coach whose identity/class is uncertain.
        return None
    def choose(coach,seat,kind):
        before=seat_modal_state(page)
        selected=before.get('selected') or {}
        known_choice=kind in ('primary','known_alternative') and any(c==coach and seat in seats for c,seats in PREFERRED_SEAT_GROUPS)
        class_ok=before.get('comfortMap') or (known_choice and before.get('detailComfort'))
        if selected=={'coach':coach,'seat':seat} and before.get('activeCoach')==coach and class_ok:
            return {'status':'primary_seat_selected' if kind=='primary' else 'alternative_seat_selected','selection':selected,'selectionKind':kind,'bookingAuthorized':False,'coachReports':reports,'message':'Platz bereits ausgewählt; nicht bestätigt oder gebucht.'}
        if before.get('activeCoach')!=coach or not class_ok:
            return None
        control=seat_modal_state(page,{'kind':'seat','value':seat,'allowKnown':known_choice})
        if control is None: return None
        control.click(timeout=5000)
        for _ in range(8):
            page.wait_for_timeout(250)
            if seat_modal_state(page).get('selected')=={'coach':coach,'seat':seat}:
                return {'status':'primary_seat_selected' if kind=='primary' else 'alternative_seat_selected','selection':{'coach':coach,'seat':seat},'selectionKind':kind,'bookingAuthorized':False,'coachReports':reports,'message':'Platz ausgewählt; nicht bestätigt oder gebucht.'}
        # An uncertain click must never be followed by further seat clicks.
        raise Blocked('Sitzplatzauswahl nicht eindeutig bestätigt.')
    selected=state.get('selected') or {}
    if selected.get('coach')=='11' and selected.get('seat') in PRIMARY_SEATS and (state.get('comfortMap') or state.get('detailComfort')):
        return {'status':'primary_seat_selected','selection':selected,'bookingAuthorized':False,'message':'Wunschplatz bereits ausgewählt; nicht bestätigt oder gebucht.'}
    candidates=[]
    scanned=set()
    def scan(coach):
        current=open_coach(coach)
        scanned.add(coach)
        if current is None:
            observed=seat_modal_state(page)
            reports.append({'coach':coach,'verified':False,'activeCoach':observed.get('activeCoach'),'comfortMap':observed.get('comfortMap'),'detailComfort':observed.get('detailComfort')})
            return None
        eligible=ranked_layout_seats(current) if current.get('comfortMap') else []
        reports.append({'coach':coach,'verified':True,'comfortMap':current.get('comfortMap'),'detailComfort':current.get('detailComfort'),'preferredSeats':[c for c in current['controls'] if c['kind']=='seat' and c['value'] in ('233A','233D','191D','182A')],'verifiedLayoutSeats':len(eligible)})
        candidates.extend((rank,coach,seat) for rank,seat in eligible)
        return current
    for coach,seats in PREFERRED_SEAT_GROUPS:
        current=scan(coach)
        if current is None: continue
        for seat in seats:
            result=choose(coach,seat,'primary' if coach=='11' else 'known_alternative')
            if result is not None: return result
    # All visible coach controls, but never assume a wagon has Comfort seats.
    for c in state.get('controls',[]):
        if c.get('kind')=='coach' and c['value'] not in scanned and not c.get('disabled'):
            scan(c['value'])
    for rank,coach,seat in sorted(set(candidates)):
        current=open_coach(coach)
        if current is None or (rank,seat) not in ranked_layout_seats(current): continue
        result=choose(coach,seat,'facing_table' if rank==0 else 'offset_facing')
        if result is not None: return result
    return blocked('Kein eindeutig freier Wunsch- oder nachweislich passender Zweierplatz. Viererplätze und unbekannte Anordnungen ausgeschlossen.')



def detail_selection_summary(page, day, expected=None):
    """Verify one complete selection card, not merely its sticky price footer."""
    if not is_review_detail_url(page.evaluate('window.location.href'),day):
        return {'verified':False,'reason':'detail_page_mismatch'}
    data=page.evaluate(r"""() => {
      const norm=s=>(s||'').replace(/[\u200B-\u200F\u202A-\u202E\u2060-\u206F]/g,'').replace(/\s+/g,' ').trim();
      const vis=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
      const text=e=>norm(e.innerText||e.textContent);
      const label=e=>norm(e.getAttribute('aria-label')||e.innerText||e.textContent||e.value);
      const titles=[...document.querySelectorAll('body *')].filter(e=>vis(e)&&text(e)==='Meine Auswahl'&&![...e.children].some(c=>vis(c)&&text(c)==='Meine Auswahl'));
      const carts=[...document.querySelectorAll('button,a[href],[role="button"],[role="link"],input[type="submit"]')].filter(e=>vis(e)&&label(e)==='In den Warenkorb');
      const parse=t=>{
        const seats=[...t.matchAll(/Sitzpl(?:atz|ätze|aetze)\s*:?\s*(\d{2,4})\s*([A-D])\b/gi)].map(m=>m[1]+m[2].toUpperCase());
        const prices=[...t.matchAll(/(?:€\s*(\d+(?:[.,]\d{2}))|(\d+(?:[.,]\d{2}))\s*€)/g)].map(m=>m[1]||m[2]);
        return {comfort:/Reservierung\s*Comfort\s*Class/i.test(t),quantityOne:/\b1\s*(?:×\s*)?Reservierung\s*Comfort\s*Class/i.test(t),
          route:/Wien\s+Meidling/i.test(t)&&/Wiener\s+Neustadt/i.test(t),train:/\b1009\b/.test(t),
          time:/18\s*:\s*22\s*[-–—−]\s*18\s*:\s*49/.test(t),dates:[...t.matchAll(/\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b/g)].map(m=>m[0].replace(/\s/g,'')),seats,prices};
      };
      const diagnostics={found:false,titleCount:titles.length,cartControlCount:carts.length,regions:[]};
      if(titles.length!==1||carts.length!==1)return diagnostics;
      // A heading and sticky footer can share a nested wrapper while the
      // product row is a sibling. Walk outward, but never accept the entire
      // page or a region containing the separate paid-product/seat form.
      let common=titles[0];
      while(common&&common!==document.body&&!common.contains(carts[0]))common=common.parentElement;
      for(let card=common,depth=0;card&&card!==document.body&&depth<9;card=card.parentElement,depth++){
        const walker=document.createTreeWalker(card,NodeFilter.SHOW_TEXT);
        const fragments=[];
        for(let n=walker.nextNode();n;n=walker.nextNode()){
          const p=n.parentElement;
          if(p&&vis(p)&&!p.closest('script,style,[hidden]')&&norm(n.textContent))fragments.push(norm(n.textContent));
        }
        const strings=[text(card),norm(fragments.join(' '))];
        const variants=strings.map(parse);
        const nonzero=variants.some(p=>p.prices.some(x=>!['0,00','0.00'].includes(x)));
        const outsideForm=strings.some(t=>/\bSitzplatzreservierung\b|pro\s*Person|Viertische\s+mit\s+mehr\s+Beinfreiheit/i.test(t));
        const tooBroad=strings.some(t=>t.length>2600);
        const region={depth,nonzero,outsideForm,tooBroad,variants};
        diagnostics.regions.push(region);
        if(outsideForm||tooBroad||nonzero)break;
        // Select the first complete region only. An incomplete sticky footer
        // is not a valid card even when its total happens to be zero.
        if(variants.some(p=>p.comfort&&p.quantityOne&&p.route&&p.train&&p.time&&p.dates.length&&p.seats.length&&p.prices.length>=2)){
          return {...diagnostics,found:true,cardCount:1,nonzero,variants};
        }
      }
      return diagnostics;
    }""")
    wanted=date.fromisoformat(day)
    allowed_dates={wanted.strftime('%d.%m.%Y'),f'{wanted.day}.{wanted.month}.{wanted.year}'}
    candidates=data.get('variants',[])
    for p in candidates:
        prices=p.get('prices',[])
        seats=list(set(p.get('seats',[])))
        date_ok=bool(p.get('dates')) and set(p['dates']).issubset(allowed_dates)
        if (data.get('found') and not data.get('nonzero') and p.get('comfort') and p.get('quantityOne') and p.get('route') and p.get('train') and p.get('time') and date_ok and len(prices)>=2 and all(x in ('0,00','0.00') for x in prices) and len(seats)==1 and (expected is None or seats==[expected])):
            return {'verified':True,'seat':seats[0],'priceCents':0,'dateVerified':True,'checks':data}
    return {'verified':False,'priceCents':None,'reason':'summary_fields_unverified','checks':data}



def detail_seat_map_entry_check(page, day):
    """Read-only entry gate for the seat map; NOT an end-price check or checkout."""
    if not is_review_detail_url(page.evaluate('window.location.href'),day):
        return {'verified':False,'reason':'detail_page_mismatch','bookingAuthorized':False}
    data=page.evaluate(r"""() => {
      const norm=s=>(s||'').replace(/[\u200B-\u200F\u202A-\u202E\u2060-\u206F]/g,'').replace(/\s+/g,' ').trim();
      const vis=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
      const text=e=>norm(e.innerText||e.textContent);
      const titles=[...document.querySelectorAll('body *')].filter(e=>vis(e)&&text(e)==='Meine Auswahl'&&![...e.children].some(c=>vis(c)&&text(c)==='Meine Auswahl'));
      const carts=[...document.querySelectorAll('button,a[href],[role="button"],[role="link"],input[type="submit"]')].filter(e=>vis(e)&&norm(e.getAttribute('aria-label')||e.innerText||e.textContent||e.value)==='In den Warenkorb');
      const result={titleCount:titles.length,cartCount:carts.length,footerUnique:false,footerZero:false,route:false,train:false,dates:[],time:false,seatSection:false};
      if(titles.length!==1||carts.length!==1)return result;
      let common=titles[0];
      while(common&&common!==document.body&&!common.contains(carts[0]))common=common.parentElement;
      if(!common||common===document.body)return result;
      const footer=text(common);
      const prices=[...footer.matchAll(/(?:€\s*(\d+(?:[.,]\d{2}))|(\d+(?:[.,]\d{2}))\s*€)/g)].map(m=>m[1]||m[2]);
      // Only the zero-priced selection footer is used to permit opening the
      // seat map. A distinct paid offer elsewhere on the page is not a total.
      result.footerUnique=footer.length<900&&prices.length>=1;
      result.footerZero=result.footerUnique&&prices.every(v=>v==='0,00'||v==='0.00');
      const body=text(document.body);
      result.route=/Wien\s+Meidling/i.test(body)&&/Wiener\s+Neustadt/i.test(body);
      result.train=/\b1009\b/.test(body);
      result.time=/18\s*:\s*22\s*[-–—−]\s*18\s*:\s*49/.test(body);
      result.dates=[...body.matchAll(/\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b/g)].map(m=>m[0].replace(/\s/g,''));
      result.seatSection=[...document.querySelectorAll('body *')].some(e=>vis(e)&&text(e)==='Sitzplatzreservierung'&&![...e.children].some(c=>vis(c)&&text(c)==='Sitzplatzreservierung'));
      return result;
    }""")
    d=date.fromisoformat(day)
    expected={d.strftime('%d.%m.%Y'),f'{d.day}.{d.month}.{d.year}'}
    date_ok=bool(data.get('dates')) and all(x in expected for x in data['dates'])
    verified=bool(data.get('titleCount')==1 and data.get('cartCount')==1 and data.get('footerUnique') and data.get('footerZero') and data.get('route') and data.get('train') and data.get('time') and data.get('seatSection') and date_ok)
    return {'verified':verified,'bookingAuthorized':False,'checks':data,'dateVerified':date_ok,
            'message':'Nur Sitzplanöffnung erlaubt. Endpreis, bestehende Reservierung und Checkout nicht geprüft.'}

def confirm_review_selection(page,day):
    """Confirm the seat within the dialog only; never add to basket or buy."""
    summary=detail_selection_summary(page,day)
    if not summary['verified']:
        return {'status':'seat_confirmation_blocked','bookingAuthorized':False,'summary':summary,'message':'Detailzusammenfassung nicht eindeutig 0 EUR; keine Bestätigung.'}
    state=seat_modal_state(page)
    selected=state.get('selected') or {}
    # A pre-approved seat is eligible; unknown layout is not accepted here.
    if not any(coach==selected.get('coach') and selected.get('seat') in seats for coach,seats in PREFERRED_SEAT_GROUPS):
        return {'status':'seat_confirmation_blocked','bookingAuthorized':False,'message':'Kein eindeutig freigegebener Wunsch-/Ersatzplatz ausgewählt.'}
    control=seat_modal_state(page,{'kind':'confirm'})
    if control is None:
        return {'status':'seat_confirmation_blocked','bookingAuthorized':False,'message':'Bestätigen im Sitzplandialog nicht eindeutig.'}
    control.click(timeout=5000)
    for _ in range(12):
        page.wait_for_timeout(250)
        if not seat_modal_state(page).get('modalFound'):
            summary=detail_selection_summary(page,day,selected['seat'])
            if summary['verified']:
                return {'status':'seat_confirmed','selection':selected,'summary':summary,'bookingAuthorized':False,'message':'Sitzplatz in Detailauswahl bestätigt; nicht im Warenkorb und nicht gebucht.'}
    return {'status':'seat_confirmation_unverified','bookingAuthorized':False,'message':'Auswahl nach Bestätigung nicht eindeutig. Nicht fortfahren.'}




def find_seat_change_control(page, diagnostic=False):
    """Locate only one editor entry within the seat-reservation section.

    The live UI may set ARIA labels on the visible "Ändern" text, use a
    framework click handler on a span, or expose the selected seat code as a
    clickable element. Never click a page-wide, unscoped control.
    """
    script=r"""(audit) => {
      const norm=s=>(s||'').normalize('NFKC').replace(/[\u200B-\u200F\u202A-\u202E\u2060-\u206F]/g,'').replace(/\s+/g,' ').trim();
      const visible=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
      const raw=e=>norm(e.innerText||e.textContent||'');
      const names=e=>[raw(e),e.getAttribute('aria-label'),e.getAttribute('title'),e.getAttribute('data-tooltip')].map(norm).filter(Boolean);
      const disabled=e=>e.matches(':disabled,[aria-disabled="true"]')||!!e.closest('[inert],[aria-disabled="true"]')||getComputedStyle(e).pointerEvents==='none';
      const editor=/^(?:(?:sitzplatz(?:reservierung)?|platz)\s+)?(?:ändern|bearbeiten|edit)(?:\s+(?:sitzplatz|platz))?$/i;
      const seat=/^(?:Sitzplatz\s*:?\s*)?(\d{2,4})\s*([A-D])$/i;
      const controls='a,button,[role="button"],[role="link"],[tabindex]';
      const all=[...document.querySelectorAll('body *')].filter(visible);
      const isSmall=e=>raw(e).length<100;
      const leaf=(value)=>all.filter(e=>raw(e)===value&&!Array.from(e.children).some(c=>visible(c)&&raw(c)===value));
      const headings=leaf('Sitzplatzreservierung');
      // The UI may nest a span inside a button and both have the same
      // "Ändern" text. Keep only the deepest labelled element; clickOwner
      // later recovers its interactive ancestor.
      const editLabels=all.filter(e=>isSmall(e)&&names(e).some(n=>editor.test(n))&&!Array.from(e.children).some(c=>visible(c)&&names(c).some(n=>editor.test(n))));
      const changedText=all.filter(e=>isSmall(e)&&editor.test(raw(e)));
      const candidates=[];
      const seatCandidates=[];
      const editorEvidence=[];
      const visualEditCandidates=[];
      const headingCenter=headings.length===1?headings[0].getBoundingClientRect():null;
      const nearEditLabels=headingCenter?editLabels.filter(e=>{const b=e.getBoundingClientRect();return b.left>=headingCenter.left-25&&Math.abs((headingCenter.top+headingCenter.bottom-b.top-b.bottom)/2)<=85;}):[];
      const sectionFacts={seatCodes:0,editorAria:0,interactiveElements:0,seatColumnLabels:0};
      const clickOwner=(el,stop)=> {
        for(let e=el;e&&e!==stop.parentElement;e=e.parentElement){
          if(e.matches(controls)||e.hasAttribute('onclick')||getComputedStyle(e).cursor==='pointer'){
            if(!disabled(e))return e;
            return null;
          }
        }
        return null;
      };
      const commonRow=(h,e,maxLength,maxHeight,verticalDistance,maxDepth)=>{
        let row=h,depth=0;
        while(row&&row!==document.body&&!row.contains(e)&&depth<maxDepth){row=row.parentElement;depth++;}
        if(!row||row===document.body||!row.contains(e))return null;
        const hr=h.getBoundingClientRect(),er=e.getBoundingClientRect(),rr=row.getBoundingClientRect();
        const dy=Math.abs((hr.top+hr.bottom-er.top-er.bottom)/2);
        if(dy>Math.min(verticalDistance,85)||er.left<hr.left-25)return null;
        // WESTbahn renders the heading and edit action in different grid
        // columns. Their nearest shared DOM ancestor may contain the entire
        // seat section, including the amenities and the 7.90 EUR offer.
        // Prefer same-row screen geometry over arbitrary 200px/380-char caps.
        if(raw(row).length>1800||rr.width>1600)return null;
        if(/Meine Auswahl|In den Warenkorb|Abbrechen|Bestätigen/.test(raw(row)))return null;
        return row;
      };
      if(headings.length===1){
        const h=headings[0];
        for(const c of editLabels){
          if(c===h||c.contains(h))continue;
          const row=commonRow(h,c,380,200,100,9);
          // The actual WESTbahn "Ändern" may sit lower than the
          // header on certain viewport widths. A second, structural
          // verification is allowed only when the common ancestor is a
          // bounded seat-information region, not the entire page.
          let shared=h,depth=0;
          while(shared&&shared!==document.body&&!shared.contains(c)&&depth<14){shared=shared.parentElement;depth++;}
          const scope=shared&&shared!==document.body?raw(shared):'';
          const hasSeatSummary=/\bWagen\b/i.test(scope)&&/\bPlatz\b/i.test(scope)&&/\b\d{2,4}\s*[A-D]\b/i.test(scope);
          const hasCheckout=/Meine Auswahl|In den Warenkorb|Bezahlen|Checkout|Jetzt kaufen|Bestätigen|Abbrechen/i.test(scope);
          const bounded=!!shared&&shared!==document.body&&scope.length<=4600&&scope.length>=25&&depth<=13;
          const semantic=bounded&&hasSeatSummary&&!hasCheckout;
          const target=row?clickOwner(c,row):semantic?clickOwner(c,shared):null;
          const usable=!!target&&!target.contains(h)&&raw(target).length<120;
          if(editorEvidence.length<8){
            const hb=h.getBoundingClientRect(),cb=c.getBoundingClientRect();
            editorEvidence.push({distanceY:Math.round((cb.top+cb.bottom-hb.top-hb.bottom)/2),
              commonDepth:shared===document.body?-1:depth,scopeCharacters:scope.length,
              bounded,hasSeatSummary,hasCheckout,linkedByRow:!!row,
              targetKind:target?target.tagName.toLowerCase():null,usable});
          }
          if(usable)candidates.push(target);
        }
        // The real WESTbahn grid can place the seat-edit link in a separate
        // DOM column sharing an ancestor with the basket. In that case, use
        // *only* a visible leaf 'Ändern' on the same on-screen heading row.
        // Never use the unrelated travel-data editor higher up the page.
        if(new Set(candidates).size===0){
          // The heading must belong to a real seat-summary region; visual
          // proximity alone must never authorize an unrelated page editor.
          let localSeatSummary=false;
          for(let ancestor=h.parentElement;ancestor&&ancestor!==document.body;ancestor=ancestor.parentElement){
            const s=raw(ancestor);
            if(s.length>3500)break;
            if(/\bWagen\b/i.test(s)&&/\bPlatz\b/i.test(s)&&/\b[0-9]{3}[A-D]\b/.test(s)){
              localSeatSummary=true;break;
            }
          }
          const hb=h.getBoundingClientRect();
          const visualLeaves=localSeatSummary?changedText.filter(e=>
            /^Ändern$/i.test(raw(e)) &&
            ![...e.children].some(child=>visible(child)&&/^Ändern$/i.test(raw(child)))):[];
          for(const c of visualLeaves){
            const cb=c.getBoundingClientRect();
            const dy=Math.abs((cb.top+cb.bottom-hb.top-hb.bottom)/2);
            if(dy>56||cb.left<hb.right-25||cb.left>hb.right+650)continue;
            const target=clickOwner(c,document.body);
            if(!target||target.contains(h)||raw(target).length>90||!/Ändern/i.test(raw(target)))continue;
            visualEditCandidates.push(target);
          }
          if(new Set(visualEditCandidates).size===1)candidates.push(visualEditCandidates[0]);
        }
        // Only if there are no matching editor labels in this section:
        // prefer the uniquely clickable selected seat number in Wagen/Platz.
        if(new Set(candidates).size===0){
          for(let section=h.parentElement,depth=0;section&&section!==document.body&&depth<9;section=section.parentElement,depth++){
            const t=raw(section);
            if(t.length>1650||/Meine Auswahl|In den Warenkorb|Abbrechen|Bestätigen/.test(t))break;
            const seatCols=/\bWagen\b/i.test(t)&&/\bPlatz\b/i.test(t);
            if(!seatCols)continue;
            sectionFacts.seatColumnLabels++;
            const descendants=[...section.querySelectorAll('*')].filter(e=>visible(e)&&raw(e).length<=75);
            sectionFacts.interactiveElements+=descendants.filter(e=>e.matches(controls)||getComputedStyle(e).cursor==='pointer').length;
            const leafSeats=descendants.filter(e=>names(e).some(n=>seat.test(n))&&!Array.from(e.children).some(c=>visible(c)&&names(c).some(n=>seat.test(n))));
            sectionFacts.seatCodes+=leafSeats.length;
            sectionFacts.editorAria+=descendants.filter(e=>names(e).some(n=>editor.test(n))).length;
            for(const e of leafSeats){
              const target=clickOwner(e,section);
              if(!target||target.contains(h)||raw(target).length>120)continue;
              const href=target.getAttribute('href');
              if(href&&href!=='#'){
                let u;
                try{u=new URL(href,document.baseURI);}catch{continue;}
                if(u.origin!==location.origin||!u.pathname.startsWith('/reservierung/sitzplatz-upgrade/'))continue;
              }
              seatCandidates.push(target);
            }
            // First bounded Wagen/Platz section prevents crossing into other cards.
            break;
          }
        }
      }
      const editUnique=[...new Set(candidates)];
      const seatUnique=[...new Set(seatCandidates)];
      const selected=editUnique.length===1?editUnique[0]:(editUnique.length===0&&seatUnique.length===1?seatUnique[0]:null);
      if(audit)return {
        seatHeadingCount:headings.length,changeLabelCount:changedText.length,
        editorLabelCandidates:editLabels.length,nearbyEditLabels:nearEditLabels.length,matchedControls:editUnique.length,
        editorEvidence,visualEditCandidates:[...new Set(visualEditCandidates)].length,
        seatLinkCandidates:seatUnique.length,seatCodeCount:sectionFacts.seatCodes,
        seatColumnLabels:sectionFacts.seatColumnLabels,editorAria:sectionFacts.editorAria,
        interactiveElements:sectionFacts.interactiveElements,
        selectedMode:selected?(editUnique.includes(selected)?'change':'seat_link'):null,
        reason:selected?'unique_editor_control':'editor_not_unique_or_not_in_section'
      };
      return selected;
    }"""
    if diagnostic:
        return page.evaluate(script,True)
    return page.evaluate_handle(script,False).as_element()


def open_review_seat_map(page, day):
    """Open the official zero-price Comfort detail and seat picker, not checkout."""
    def live_url(p):
        return p.evaluate('window.location.href')
    def matching_details():
        return [p for p in page.context.pages if not p.is_closed() and is_review_detail_url(live_url(p),day)]
    details=matching_details()
    if len(details)>1: raise Blocked('Mehrere passende Detailseiten. Keine weitere Auswahl.')
    if not details:
        u=urlsplit(live_url(page))
        if u.scheme!='https' or u.hostname!='westbahn.at' or u.username or u.password or u.port not in (None,443) or u.path.rstrip('/')!='/reservierung/sitzplatz-upgrade' or parse_qs(u.query).get('do')!=[day]:
            raise Blocked('Suchseite oder Datum nicht eindeutig. Keine Comfort-Auswahl.')
        # Read the current search again rather than trusting an earlier 0-EUR result.
        result=read_loaded_connection(page,day)
        conn=(result or {}).get('connection',{})
        if (conn.get('date')!=day or conn.get('trainNumber')!='1009' or conn.get('departure')!='18:22' or conn.get('arrival')!='18:49' or conn.get('displayedPriceCents')!=0 or conn.get('priceSource')!='comfort_control'):
            raise Blocked('Aktuelle Comfort-Verbindung nicht eindeutig 0 EUR. Keine Auswahl.')
        inspection=comfort_control_details(page,conn)
        fresh=apply_comfort_control_price(dict(conn,displayedPriceCents=None,priceStatus='not_displayed',priceSource=None),inspection)
        if fresh.get('displayedPriceCents')!=0 or fresh.get('priceSource')!='comfort_control':
            raise Blocked('Comfort-Button nicht eindeutig 0 EUR. Keine Auswahl.')
        control=comfort_control_details(page,conn,return_button=True)
        if control is None: raise Blocked('Comfort-Button nicht eindeutig.')
        # The official UI may create a provisional basket/selection on this click.
        # Never click it again automatically after a timeout.
        control.click(timeout=5000)
        for _ in range(24):
            page.wait_for_timeout(250)
            details=matching_details()
            if details: break
    if len(details)!=1: raise Blocked('Detailseite nach Comfort-Auswahl nicht eindeutig. Nicht erneut klicken.')
    actual=details[0]
    if seat_modal_state(actual).get('modalFound'): return actual
    summary=detail_selection_summary(actual,day)
    for _ in range(12):
        if summary.get('verified'): break
        actual.wait_for_timeout(250)
        summary=detail_selection_summary(actual,day)
    if not summary.get('verified'):
        # This read-only navigation gate is deliberately weaker than a
        # booking-price check, and never authorizes a purchase.
        entry=detail_seat_map_entry_check(actual,day)
        if not entry.get('verified'):
            raise Blocked('Sitzplanöffnung gesperrt: '+json.dumps({'entry':entry,'detail':summary},ensure_ascii=False))
    # Use the heading-row label even if WESTbahn renders it as a span or an
    # anchor without href. Never select an unscoped page-wide 'Ändern'.
    change=find_seat_change_control(actual)
    if change is None:
        audit=find_seat_change_control(actual,diagnostic=True)
        raise Blocked('Ändern im Sitzplatzbereich nicht eindeutig. Diagnose: '+json.dumps(audit,ensure_ascii=False))
    change.click(timeout=5000)
    for _ in range(16):
        actual.wait_for_timeout(250)
        if seat_modal_state(actual).get('modalFound'): return actual
    raise Blocked('Sitzplan nach Öffnen nicht eindeutig. Keine weitere Aktion.')


def safe_review_failure(error, phase):
    """Diagnostics without exception messages, URLs, credentials or page text."""
    import traceback
    source=[f for f in traceback.extract_tb(error.__traceback__) if f.filename.replace('\\\\','/').endswith('/worker.py')]
    last=source[-1] if source else None
    kind=type(error).__name__
    # JavaScript errors surface as Playwright Error, not Python TypeError.
    detail=str(error)
    if 'ReferenceError:' in detail:
        category='browser_reference_error'
    elif 'SyntaxError:' in detail:
        category='browser_syntax_error'
    elif 'TypeError:' in detail:
        category='browser_type_error'
    elif 'Timeout' in kind or 'Timeout' in detail:
        category='timeout'
    elif 'Target closed' in detail or 'context was destroyed' in detail:
        category='browser_context_changed'
    elif 'strict mode violation' in detail:
        category='ambiguous_locator'
    else:
        category='unexpected_browser_error'
    return {'phase':phase,'category':category,'exceptionClass':kind[:48],
            'workerFunction':last.name if last else None,
            'workerLine':last.lineno if last else None,
            'bookingAuthorized':False}


def manual_seat_review(page, day, root=None):
    # Login and search stay in the SAME visible browser, never a cloned profile.
    # A failed session check keeps the private desktop open for manual login.
    last_confirmed_seat=None
    while True:
        result=authenticated_prepare(page,day,root=root)
        print(json.dumps(result,ensure_ascii=False),file=sys.stderr,flush=True)
        if result.get('status') in ('login_required','account_unverified'):
            print('Bitte im privaten Browser auf westbahn.at anmelden bzw. das Konto öffnen. Danach hier Enter drücken; q beendet.',file=sys.stderr,flush=True)
            if read_review_command(page)=='q':
                return {'status':'manual_review_ended','message':'Keine automatische Buchung.'}
            continue
        if result.get('connection',{}).get('displayedPriceCents')!=0:
            print('Comfort nicht eindeutig 0 EUR. Nicht fortfahren. Im Browser Anmeldung/KlimaTicket prüfen; danach Enter für erneute Suche oder q zum Beenden.',file=sys.stderr,flush=True)
            if read_review_command(page)=='q':
                return {'status':'manual_review_ended','message':'Keine automatische Buchung.'}
            continue
        print('Konto vor der Suche bestätigt, angezeigter Preis 0 EUR. a + Enter öffnet bei Bedarf Comfort und Sitzplan und prüft/wählt den Wunschplatz, b + Enter bestätigt den Sitzplatz, c + Enter prüft den Warenkorb nur lesend. Enter allein lässt den Browser offen; q + Enter beendet. Nicht kaufen.',file=sys.stderr,flush=True)
        while True:
            command=read_review_command(page)
            if command=='q':
                break
            if command not in ('a','b','c'):
                print('Browser bleibt geöffnet. a + Enter öffnet/wählt; b + Enter bestätigt; c + Enter prüft den Warenkorb; q + Enter beendet. Kein automatischer Kauf.',file=sys.stderr,flush=True)
                continue
            phase='inspect_checkout' if command=='c' else 'locate_open_review_page'
            try:
                if command=='c':
                    checkouts=[]
                    for current in page.context.pages:
                        if current.is_closed(): continue
                        u=urlsplit(current.evaluate('window.location.href'))
                        if u.scheme=='https' and u.hostname=='westbahn.at' and u.path.rstrip('/')=='/ticketshop/checkout':
                            checkouts.append(current)
                    if len(checkouts)!=1 or not last_confirmed_seat:
                        result={'status':'cart_inspection_blocked','bookingAuthorized':False,
                                'message':'Ein eindeutiger Warenkorb und vorher bestätigter Sitzplatz fehlen.'}
                    else:
                        result={'status':'cart_inspection','seat':last_confirmed_seat,
                                **audit_cart(checkouts[0],day,last_confirmed_seat)}
                    print(json.dumps(result,ensure_ascii=False),file=sys.stderr,flush=True)
                    continue
                actual,diagnostic=find_open_review_page(page,day)
                if actual is None and command=='a':
                    phase='open_comfort_and_seat_map'
                    actual=open_review_seat_map(page,day)
                    phase='locate_opened_seat_map'
                    actual,diagnostic=find_open_review_page(actual,day)
                if actual is None:
                    result={'status':'seat_selection_blocked','bookingAuthorized':False,'inspection':diagnostic,'message':'Keine eindeutige Detailseite mit geöffnetem Sitzplan für das gewünschte Datum gefunden.'}
                else:
                    phase='confirm_seat_only' if command=='b' else 'select_preferred_seat'
                    result=confirm_review_selection(actual,day) if command=='b' else select_primary_seat_in_open_modal(actual)
                    result['pageInspection']=diagnostic
                    if result.get('status')=='seat_confirmed':
                        last_confirmed_seat=result.get('selection',{}).get('seat')
            except Blocked as error:
                result={'status':'seat_selection_blocked','bookingAuthorized':False,'message':str(error)}
            except Exception as error:
                result={'status':'seat_selection_blocked','bookingAuthorized':False,'failure':safe_review_failure(error,phase),'message':'Technischer Fehler bei der Sitzplanprüfung; Details unter failure. Keine automatische Bestätigung.'}
            print(json.dumps(result,ensure_ascii=False),file=sys.stderr,flush=True)
            print('Browser bleibt geöffnet. a + Enter Auswahl, b + Enter Sitzplatzbestätigung, c + Enter Warenkorb-Audit, q + Enter beenden. Kein automatischer Kauf.',file=sys.stderr,flush=True)
        return {'status':'manual_review_ended','message':'Manuelle Ansicht beendet. Keine automatische Buchung.'}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['login','probe','prepare','account','account-audit','comfort-inspect','seat-preview','seat-network-diagnostic','price-audit','seat-review','credentials-set','credentials-remove','login-check','booking-check','confirmation-check','ticket-detail-check','inventory-batch']);parser.add_argument('--date'); parser.add_argument('--seat'); parser.add_argument('--dates'); parser.add_argument('--page',type=int,default=None); args=parser.parse_args()
    if args.page is not None and not 1 <= args.page <= 100: raise Blocked('Ungültige Kontoseite.')
    try: batch_days=validate_batch_dates(args.dates) if args.mode=='inventory-batch' else None
    except ValueError: raise Blocked('Ungültiger Pendeltage-Bereich.')
    root=Path(os.environ.get('WESTBAHN_BROWSER_PROFILE','./data/westbahn-browser')).resolve(); root.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(root,0o700)
    os.umask(0o077)
    with (root/'.agent.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise Blocked('Browserprofil ist gerade in Benutzung.')
        if args.mode=='credentials-set': return configure_login(root)
        if args.mode=='credentials-remove':
            credential_path(root).unlink(missing_ok=True)
            (root/'.login-attempt').unlink(missing_ok=True)
            return {'status':'credentials_removed','message':'Gespeicherte Zugangsdaten entfernt; Browseranmeldung separat.'}
        with sync_playwright() as p:
            kwargs={'headless':args.mode not in ('login','seat-review'),'timeout':20000,'accept_downloads':False}
            if os.environ.get('WESTBAHN_CHROMIUM_PATH'): kwargs['executable_path']=os.environ['WESTBAHN_CHROMIUM_PATH']
            if args.mode=='price-audit':
                if not args.date: raise Blocked('Reisedatum fehlt.')
                return run_price_audit(p,root,kwargs,args.date)
            if args.mode in ('seat-preview','seat-network-diagnostic'):
                if not args.date: raise Blocked('Reisedatum fehlt.')
                return run_seat_preview(p,root,kwargs,args.date,network_diagnostic=args.mode=='seat-network-diagnostic')
            context=p.chromium.launch_persistent_context(str(root/'chromium'),**kwargs)
            try:
                page=context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(5000)
                if args.mode not in ('login','seat-review'):
                    # Restrict automated top-level navigations; no external authentication flow.
                    def guard(route):
                        if args.mode=='inventory-batch' and route.request.method.upper() not in ('GET','HEAD'):
                            route.abort()
                            return
                        if route.request.is_navigation_request():
                            try: subframe=route.request.frame.parent_frame is not None
                            except Exception: subframe=False
                            if not allowed_navigation(route.request.url, subframe) and not (args.mode in ('login-check','prepare','comfort-inspect','account','booking-check','confirmation-check','ticket-detail-check','inventory-batch') and trusted_login_url(route.request.url)) and not (args.mode in ('account','account-audit','booking-check','confirmation-check','ticket-detail-check','inventory-batch') and urlsplit(route.request.url).scheme=='https' and urlsplit(route.request.url).hostname=='westbahn.de' and not urlsplit(route.request.url).username and not urlsplit(route.request.url).password): 
                                route.abort()
                                return
                        route.continue_()
                    context.route('**/*',guard)
                if args.mode=='login-check': return ensure_austrian_session(page,root)
                if args.mode=='account':
                    session=ensure_austrian_session(page,root)
                    if session['status']!='account_verified': return session
                    return account_inventory(context,args.page)
                if args.mode=='account-audit':
                    if not args.date: raise Blocked('Reisedatum für Kontovergleich fehlt.')
                    return account_audit(context,args.date)
                if args.mode=='inventory-batch':
                    session=ensure_austrian_session(page,root)
                    if session.get('status')!='account_verified':
                        return {'status':'account_not_verified','days':[],
                                'inventoryComplete':False,'safeToBook':False,
                                'bookingAuthorized':False}
                    inventory=account_inventory(context,max_pages=5)
                    # Existing visible cards are only candidates, never proof
                    # that another date is free. For up to two unambiguous
                    # candidate days, re-read an actual ticket detail page.
                    # This may prove an existing booking, not an absent one.
                    preliminary=summarize_inventory_batch(
                        inventory.get('matchingVisibleCards'),batch_days,
                        inventory.get('reports'))
                    detail_checks={}
                    examined=0
                    # Prioritize uncertain, yearless cards before already dated
                    # tickets. The bounded two-detail budget must not be spent
                    # on confirmed dates while a possible duplicate remains.
                    priority={'possible_existing': 0, 'visible_year_verified': 1}
                    candidates=sorted(
                        preliminary['days'],
                        key=lambda item: priority.get(item['status'], 2))
                    for item in candidates:
                        if examined>=2: break
                        if not item['potentialDuplicate'] or len(item['seats'])!=1:
                            continue
                        examined+=1
                        try:
                            detail_checks[item['date']]=inspect_existing_ticket_details(
                                context,item['date'],item['seats'][0],max_pages=2)
                        except Exception:
                            # Ambiguity, missing year or session problems never
                            # turn a possible ticket into a booking permission.
                            pass
                    return summarize_inventory_batch(
                        inventory.get('matchingVisibleCards'),batch_days,
                        inventory.get('reports'),detail_checks)
                if args.mode=='booking-check':
                    if not args.date: raise Blocked('Reisedatum für Bestandsprüfung fehlt.')
                    session=ensure_austrian_session(page,root)
                    if session['status']!='account_verified':
                        return {'status':'account_not_verified','safeToBook':False,'message':'Konto nicht bestätigt; keine Buchung.'}
                    inventory=account_inventory(context)
                    evidence=assess_existing_ticket(inventory.get('matchingVisibleCards'),args.date,args.seat)
                    return {'status':'booking_check','date':args.date,'inventoryComplete':False,**evidence}
                if args.mode=='ticket-detail-check':
                    if not args.date or not args.seat:
                        raise Blocked('Datum und Sitzplatz für Ticketdetailprüfung fehlen.')
                    session=ensure_austrian_session(page,root)
                    if session['status']!='account_verified':
                        return {'status':'account_not_verified','confirmationVerified':False,
                                'bookingAuthorized':False,'safeToBook':False,
                                'message':'Konto nicht bestätigt; keine Ticketdetailprüfung.'}
                    return inspect_existing_ticket_details(context,args.date,args.seat)
                if args.mode=='confirmation-check':
                    if not args.date or not args.seat: raise Blocked('Datum und Sitzplatz für Bestätigungsprüfung fehlen.')
                    session=ensure_austrian_session(page,root)
                    if session['status']!='account_verified':
                        return {'status':'account_not_verified','confirmationVerified':False,'bookingAuthorized':False,
                                'message':'Konto nicht bestätigt; keine Bestätigung.'}
                    inventory=account_inventory(context)
                    return summarize_confirmation_candidates(inventory.get('matchingVisibleCards'),args.date,args.seat)
                if args.mode in ('prepare','comfort-inspect','seat-review') and not args.date: raise Blocked('Reisedatum fehlt.')
                if args.mode=='seat-review': return manual_seat_review(page,args.date,root)
                if args.mode in ('prepare','comfort-inspect'):
                    return authenticated_prepare(page,args.date,inspect_only=args.mode=='comfort-inspect',root=root)
                target=URL
                page.goto(target,wait_until='domcontentloaded',timeout=25000)
                if args.mode=='login':
                    print('Melde dich im geöffneten WESTbahn-Browser an. Danach hier Enter drücken. Keine Zugangsdaten im Terminal eingeben.',file=sys.stderr,flush=True)
                    input()
                    session=verify_austrian_session(page)
                    if session['status']!='account_verified':
                        return {'status':'profile_saved_unverified','message':'Profil gespeichert; österreichisches Konto nicht bestätigt. Keine Buchung.'}
                    return {'status':'profile_saved','accountVerified':True,'message':'Browserprofil gespeichert; österreichisches Konto aktuell bestätigt.'}
                if args.mode=='probe': return inspect(page)
                if not official(page.url): raise Blocked('Nicht erlaubte Browserseite.')
                if not args.date: raise Blocked('Reisedatum fehlt.')
                raise Blocked('Unbekannter Browsermodus.')
            finally: context.close()

if __name__=='__main__':
    try: print(json.dumps(main(),ensure_ascii=False))
    except Blocked as e: print(json.dumps({'status':'blocked','message':str(e)},ensure_ascii=False))
    except PWTimeout: print(json.dumps({'status':'blocked','message':'Zeitlimit beim WESTbahn-Suchformular. Bitte Suchfelder und Cookie-Dialog prüfen. Keine Buchung vorgenommen.'},ensure_ascii=False))
    except Exception: print(json.dumps({'status':'blocked','message':'Browser nicht verfügbar, Seite nicht erreichbar oder Ablauf nicht eindeutig. Keine Buchung vorgenommen.'},ensure_ascii=False))
