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
    
def prepare(page, day):
    day=date.fromisoformat(day).isoformat()
    dismiss_cookie_dialog(page)
    set_station(page,'Von',ORIGIN)
    set_station(page,'Nach',DESTINATION)
    if normalize_station(field(page,'Von').input_value()) not in {normalize_station(n) for n in STATION_LABELS[ORIGIN]} or normalize_station(field(page,'Nach').input_value()) not in {normalize_station(n) for n in STATION_LABELS[DESTINATION]}:
        raise Blocked('Bahnhofsauswahl hat sich geändert. Keine Suche.')
    confirm_date(page, day)
    # Only search, never add to cart or confirm purchase. Exact single button required.
    search=unique([page.get_by_role('button',name='Verbindung suchen',exact=True)],'Verbindung suchen')
    search.click(timeout=5000)
    return {'status':'search_submitted','message':'Suchanfrage ausgelöst; Abfahrt 18:22, Verfügbarkeit, Klasse, Sitzplatz und Preis sind noch nicht verifiziert. Keine Buchung.'}

def inspect(page):
    if not official(page.url): raise Blocked('Browser außerhalb der erlaubten WESTbahn-Domain.')
    return {'status':'reachable','message':'Offizielle WESTbahn-Seite im Chromium geöffnet. Keine Anmeldung, Verfügbarkeit oder Buchung bestätigt.', 'originField': any(x.count()==1 and x.is_visible() for x in [page.get_by_label('Von',exact=True),page.get_by_placeholder('Von',exact=True)]),'destinationField':any(x.count()==1 and x.is_visible() for x in [page.get_by_label('Nach',exact=True),page.get_by_placeholder('Nach',exact=True)])}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['login','probe','prepare']);parser.add_argument('--date'); args=parser.parse_args()
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
                            if not allowed_navigation(route.request.url, subframe): 
                                route.abort()
                                return
                        route.continue_()
                    context.route('**/*',guard)
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
