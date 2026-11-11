"""Redacted conservative assessment of visible WESTbahn account cards.

No missing card can authorize booking; no result indicates inventory completeness.
"""
from datetime import date
from booking_evidence import assess_existing_ticket


def validate_batch_dates(value):
    """Accept up to five unique ISO weekdays, never use uncontrolled page ranges."""
    if not isinstance(value,str):
        raise ValueError('invalid_dates')
    dates=value.split(',')
    if not (1 <= len(dates) <= 5) or len(set(dates)) != len(dates):
        raise ValueError('invalid_dates')
    for text in dates:
        try:
            day=date.fromisoformat(text)
        except (TypeError,ValueError):
            raise ValueError('invalid_dates') from None
        if day.isoformat()!=text or day.weekday()>4:
            raise ValueError('invalid_dates')
    return dates


def summarize_inventory_batch(rows, days, reports):
    """Fixed-shape report. Never serialize the cards, links, names, refs or IDs."""
    if not isinstance(days,list) or not 1<=len(days)<=5 or any(
       not isinstance(day,str) for day in days):
        raise ValueError('invalid_dates')
    page_reports=reports if isinstance(reports,list) else []
    successful=sum(1 for r in page_reports
                   if isinstance(r,dict) and r.get('status')=='account_verified')
    output=[]
    for day in days:
        result=assess_existing_ticket(rows,day)
        matching=result.get('matches',[])
        seen=result.get('status')=='existing_ticket_visible' and bool(matching)
        seats=sorted({r['seat'] for r in matching
                     if isinstance(r,dict) and isinstance(r.get('seat'),str)})
        # Yearless labels are a potential reservation conflict, not proof
        # of a specific year. A missing result stays pending manual review.
        exact=seen and all(x.get('yearExplicit') is True for x in matching)
        output.append({
            'date':day,
            'status':('visible_year_verified' if exact else
                      'possible_existing' if seen else 'review_required'),
            'seats':seats if seen else [],
            'dateVerified':bool(exact),
            'potentialDuplicate':bool(seen),
            'safeToBook':False
        })
    return {
        'status':'inventory_batch_read' if successful else 'account_unavailable',
        'days':output,
        'accountPageReads':successful,
        'inventoryComplete':False,
        'safeToBook':False,
        'bookingAuthorized':False,
        'message':'Sichtbare Kontokarten geprüft. Fehlende Treffer erlauben keine Buchung.'
    }
