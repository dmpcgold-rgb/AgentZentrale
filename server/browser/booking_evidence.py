"""Conservative evidence from read-only WESTbahn ticket cards.

An absence in the displayed account pages is never proof that a reservation
does not exist. This module cannot authorize a new booking.
"""
import re
from datetime import date

MONTHS=('JAN','FEB','MÄR','APR','MAI','JUN','JUL','AUG','SEP','OKT','NOV','DEZ')
WEEKDAYS=('MO','DI','MI','DO','FR','SA','SO')


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
        matches.append({'seat':seat, 'yearExplicit':bool(hit.group(1)),
                        'expectedSeat':expected_seat is None or expected_seat==seat})
    if not matches:
        return {'status':'not_seen_in_incomplete_account','safeToBook':False,'matches':[],
                'message':'Keine passende sichtbare Karte; fehlender Treffer beweist keine fehlende Reservierung.'}
    return {'status':'existing_ticket_visible','safeToBook':False,'matches':matches,
            'dateFullyVerified':any(x['yearExplicit'] for x in matches),
            'message':'Passende Konto-Karte sichtbar; keine neue Buchung für dieses Datum starten. Jahreslose Karten nicht als vollständigen Beleg behandeln.'}
