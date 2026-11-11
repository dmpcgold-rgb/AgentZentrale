"""Redacted, fixed-vocabulary route diagnostics for ticket detail candidates.

No URL, token, query value, account name, order number, or free-form caption
ever appears in returned diagnostics. It performs no browser interaction.
"""
from urllib.parse import urljoin, urlsplit, parse_qsl
import re

STATIC_SEGMENTS=frozenset((
    'ticketshop','dashboard','tickets','ticket','reservierung','reservierungen',
    'reservation','reservations','details','detail','view','show','display',
    'booking','bookings','orders','order','account','mytickets','my',
    'download','pdf','print','invoice','receipt','beleg','ticketdetails',
    'profile','manage','manage-ticket','storno','cancel','checkout','shop'
))
KNOWN_QUERY_KEYS=frozenset(('id','ticketid','ticket','bookingid','reservationid','ref','page','mode'))


def token_length_band(value):
    """Coarse lengths only, never the value or its exact length."""
    n=len(value)
    if n<=3: return '1-3'
    if n<=7: return '4-7'
    if n<=11: return '8-11'
    if n<=90: return '12-90'
    return 'over90'


def observed_ticket_shape(pieces):
    """Diagnose the live two-token ticket path without revealing identifiers."""
    if len(pieces)!=5 or [p.lower() for p in pieces[:3]]!=['ticketshop','dashboard','ticket']:
        return None
    opaque=pieces[-2:]
    bands='|'.join(token_length_band(v) for v in opaque)
    charset='token_ascii' if all(re.fullmatch(r'[A-Za-z0-9_-]+',v) for v in opaque) else 'other_or_encoded'
    return bands+';'+charset


def route_signature(base, href, tag='a'):
    """Return only a stable structural fingerprint from an unknown link."""
    kind = 'anchor' if tag=='a' else 'button' if tag=='button' else 'other_control'
    if kind!='anchor':
        return {'kind':kind,'route':'not_applicable','query':'not_applicable'}
    if not isinstance(href,str) or not href or len(href)>1000:
        return {'kind':kind,'route':'no_destination','query':'none'}
    try:
        source=urlsplit(base)
        target=urlsplit(urljoin(base,href))
        if not (source.scheme=='https' and source.hostname in ('westbahn.at','westbahn.de')
                and target.scheme=='https' and target.hostname==source.hostname
                and target.port in (None,443) and not target.username and not target.password):
            return {'kind':kind,'route':'outside_same_official_host','query':'redacted'}
        pieces=target.path.strip('/').split('/') if target.path.strip('/') else []
        safe=[p.lower() if p.lower() in STATIC_SEGMENTS else '[opaque]' for p in pieces[:8]]
        if len(pieces)>8: safe.append('[more]')
        route='/'+'/'.join(safe)
        keys=[k.lower() for k,_ in parse_qsl(target.query,keep_blank_values=True)]
        query='none' if not keys else (
            'known_only' if all(k in KNOWN_QUERY_KEYS for k in keys) else 'includes_other_keys'
        )
        result={'kind':kind,'route':route[:180], 'query':query}
        shape=observed_ticket_shape(pieces)
        if shape is not None:
            result['ticketRouteShape']=shape
        return result
    except (ValueError,TypeError):
        return {'kind':kind,'route':'invalid_destination','query':'redacted'}
