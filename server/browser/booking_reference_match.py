"""Exact booking-reference comparison against a read-only provider ticket page.

No booking IDs or customer references leave this module. Callers receive only
boolean evidence. Reference matching alone never proves a reservation.
"""
import re

REFERENCE_FIELD = re.compile(
    r'\b(?:Buchungsnummer|Bestellnummer|Reservierungsnummer|Auftragsnummer)'
    r'\s*:\s*([A-Z0-9][A-Z0-9-]{5,39})\b', re.I)
REFERENCE_FORMAT = re.compile(r'[A-Z0-9][A-Z0-9-]{5,39}', re.I)


def exact_reference_match(ticket_text, expected):
    """Return a boolean without returning, logging or normalizing away differences.

    A reference must appear once as a properly labeled field. Additional
    conflicting references or an invalid expected value fail closed.
    """
    if not isinstance(ticket_text,str) or not isinstance(expected,str):
        return False
    if not REFERENCE_FORMAT.fullmatch(expected):
        return False
    refs={m.group(1).upper() for m in REFERENCE_FIELD.finditer(ticket_text)}
    return len(refs)==1 and next(iter(refs))==expected.upper()
