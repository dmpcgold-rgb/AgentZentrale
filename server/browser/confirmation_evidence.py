"""Privacy-preserving read-only indicators of a WESTbahn order confirmation.

Account cards can show references without providing an authoritative, complete
inventory. Never expose reference values; never authorize a purchase from here.
"""
import re
from booking_evidence import assess_existing_ticket

REFERENCE_PATTERNS = {
    'bookingReference': re.compile(
        r'\b(?:Buchungsnummer|Bestellnummer|Reservierungsnummer|Auftragsnummer)\s*:?\s*'
        r'([A-Z0-9][A-Z0-9-]{5,39})\b', re.I),
    'ticketCode': re.compile(
        r'\b(?:Ticketcode|Ticket-Code)\s*:?\s*'
        r'([A-Z0-9][A-Z0-9-]{3,39})\b', re.I),
    'ticketReference': re.compile(
        r'\b(?:Ticketnummer|Ticket[- ]?ID)\s*:?\s*'
        r'([A-Z0-9][A-Z0-9-]{5,39})\b', re.I),
}


def reference_indicators(card_text):
    """Booleans only. Sensitive ticket identifiers never leave this function."""
    if not isinstance(card_text, str):
        return {'bookingReference': False, 'ticketReference': False}
    # Ticket codes alone are not booking references. Preserve the two-key API.
    return {key: bool(REFERENCE_PATTERNS[key].search(card_text))
            for key in ('bookingReference', 'ticketReference')}


def summarize_confirmation_candidates(rows, day, seat):
    """Classify visible account cards without declaring a purchase confirmed."""
    matching=assess_existing_ticket(rows,day,seat)
    visible=matching['status']=='existing_ticket_visible'
    with_seat=[m for m in matching.get('matches',[]) if m['expectedSeat']]
    exact_year=any(m['yearExplicit'] for m in with_seat)
    labeled_reference=any(m.get('bookingReference') or m.get('ticketReference') or m.get('ticketCode') for m in with_seat)
    if visible and exact_year and labeled_reference:
        evidence='dated_reference_candidate'
    elif visible:
        evidence='visible_ticket_card'
    else:
        evidence='not_proven'
    return {
        'status':'confirmation_evidence',
        'existingTicketVisible':visible,
        'yearVerified':exact_year,
        'labeledReferenceVisible':labeled_reference,
        'evidenceLevel':evidence,
        'confirmationVerified':False,
        'bookingAuthorized':False,
        'inventoryComplete':False,
        'message':'Nur Merkmale bereits vorhandener Kontokarten geprüft. Keine Anbieter-Buchungsnummer ausgelesen, keine Bestellung ausgelöst.'
    }
