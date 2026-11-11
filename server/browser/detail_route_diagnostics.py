"""Redacted, fixed-vocabulary route diagnostics for ticket detail candidates.

No URL, token, query value, account name, order number, or free-form caption
ever appears in returned diagnostics. It performs no browser interaction.
"""
from urllib.parse import urljoin, urlsplit, parse_qsl

STATIC_SEGMENTS=frozenset((
    'ticketshop','dashboard','tickets','ticket','reservierung','reservierungen',
    'reservation','reservations','details','detail','view','show','display',
    'booking','bookings','orders','order','account','mytickets','my',
    'download','pdf','print','invoice','receipt','beleg','ticketdetails',
    'profile','manage','manage-ticket','storno','cancel','checkout','shop'
))
KNOWN_QUERY_KEYS=frozenset(('id','ticketid','ticket','bookingid','reservationid','ref','page','mode'))


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
        return {'kind':kind,'route':route[:180], 'query':query}
    except (ValueError,TypeError):
        return {'kind':kind,'route':'invalid_destination','query':'redacted'}
