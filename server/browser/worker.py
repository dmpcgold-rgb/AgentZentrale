#!/usr/bin/env python3
"""Private WESTbahn browser. Read-only search; no checkout or payment actions."""
import argparse, fcntl, json, os, sys
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

URL = 'https://westbahn.at/reservierung/sitzplatz-upgrade/'
ORIGIN = 'Wien Meidling'
DESTINATION = 'Wiener Neustadt Hbf'

class Blocked(Exception): pass

def official(url):
    p=urlsplit(url)
    return p.scheme=='https' and (p.hostname=='westbahn.at' or (p.hostname or '').endswith('.westbahn.at')) and not p.username and not p.password

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
    try:
        buttons[0].click(timeout=5000)
        dialog.wait_for(state='hidden', timeout=5000)
        underlay.wait_for(state='hidden', timeout=5000)
    except PWTimeout:
        raise Blocked('Cookie-Dialog konnte nicht geschlossen werden. Keine Suche ausgeführt.')
    return True

def field(page, label):
    return unique([page.get_by_label(label,exact=True),page.get_by_placeholder(label,exact=True)],label)

def set_station(page,label,value):
    loc=field(page,label)
    loc.fill(value)
    # Only an exact station in an accessible suggestion is accepted.
    option=page.get_by_role('option',name=value,exact=True)
    try: option.wait_for(state='visible',timeout=3500)
    except PWTimeout: raise Blocked(f'Bahnhofsvorschlag für {label} nicht eindeutig bestätigt.')
    if option.count()!=1: raise Blocked(f'Mehrdeutiger Bahnhofsvorschlag: {label}.')
    option.click()
    if loc.input_value().strip()!=value: raise Blocked(f'Bahnhof {label} nicht bestätigt.')

def prepare(page, day):
    day=date.fromisoformat(day).isoformat()
    dismiss_cookie_dialog(page)
    set_station(page,'Von',ORIGIN)
    set_station(page,'Nach',DESTINATION)
    when=field(page,'Hinfahrt')
    if when.get_attribute('type')!='date': raise Blocked('Datumsauswahl ist nicht als eindeutiges Datumsfeld erkennbar.')
    when.fill(day)
    if when.input_value()!=day: raise Blocked('Datum nicht bestätigt.')
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
                        if route.request.is_navigation_request() and not official(route.request.url): route.abort()
                        else: route.continue_()
                    context.route('**/*',guard)
                page.goto(URL,wait_until='domcontentloaded',timeout=25000)
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
