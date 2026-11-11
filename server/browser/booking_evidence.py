"""Conservative evidence from read-only WESTbahn ticket cards.

An absence in the displayed account pages is never proof that a reservation
does not exist. This module cannot authorize a new booking.
"""
import re
from datetime import date

MONTHS=('JAN','FEB','MÄR','APR','MAI','JUN','JUL','AUG','SEP','OKT','NOV','DEZ')
WEEKDAYS=('MO','DI','MI','DO','FR','SA','SO')


def extract_explicit_trip_date(card_text):
    """Return ISO date only for one explicit travel-date field on this card."""
    if not isinstance(card_text,str):
        return None
    dates=set()
    for match in re.finditer(
        r'\b(?:Fahrtdatum|Reisedatum|Abfahrt(?:sdatum)?)\s*:?\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\b',
        card_text,re.I
    ):
        try:
            dates.add(date(int(match.group(3)),int(match.group(2)),int(match.group(1))).isoformat())
        except ValueError:
            continue
    return next(iter(dates)) if len(dates)==1 else None


def assess_existing_ticket(rows, requested_day, expected_seat=None):
    """Match visible weekday/month/day and optionally a seat; no ticket IDs logged."""
    try:
        day=date.fromisoformat(requested_day)
    except (ValueError, TypeError):
        return {'status':'invalid_date','safeToBook':False,'matches':[]}
    if expected_seat is not None and not re.fullmatch(r'[0-9]{3}[A-D]',expected_seat):
        return {'status':'invalid_seat','safeToBook':False,'matches':[]}
    prefix=rf'{WEEKDAYS[day.weekday()]}\s+0?{day.day}\s+{MONTHS[day.month-1]}'
    pattern=re.compile(rf'^{prefix}(?:\s+([0-9]{{4}}))?$',re.I)
    matches=[]
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,dict): continue
        label=' '.join((row.get('dateLabel') or '').split()).upper()
        hit=pattern.fullmatch(label)
        if not hit or (hit.group(1) and hit.group(1)!=str(day.year)): continue
        seat=(row.get('seat') or '').replace(' ','').upper()
        if not re.fullmatch(r'[0-9]{3}[A-D]',seat): continue
        # A real four-digit date from this ticket card can resolve a
        # yearless weekday label. Never infer the year from the current date.
        explicit=row.get('fullDate')
        if explicit is not None:
            if not isinstance(explicit,str): continue
            try:
                exact=date.fromisoformat(explicit).isoformat()
            except ValueError:
                continue
            if exact!=day.isoformat(): continue
        matches.append({'seat':seat, 'yearExplicit':bool(hit.group(1) or explicit),
                        'expectedSeat':expected_seat is None or expected_seat==seat,
                        'bookingReference':row.get('bookingReference') is True,
                        'ticketReference':row.get('ticketReference') is True})
    if not matches:
        return {'status':'not_seen_in_incomplete_account','safeToBook':False,'matches':[],
                'message':'Keine passende sichtbare Karte; fehlender Treffer beweist keine fehlende Reservierung.'}
    return {'status':'existing_ticket_visible','safeToBook':False,'matches':matches,
            'dateFullyVerified':any(x['yearExplicit'] for x in matches),
            'message':'Passende Konto-Karte sichtbar; keine neue Buchung für dieses Datum starten. Jahreslose Karten nicht als vollständigen Beleg behandeln.'}
