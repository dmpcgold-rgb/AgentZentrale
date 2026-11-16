"""Fail-closed final gate for WESTbahn unattended reservation attempts.

The UI's enabled zero-euro button is not authoritative proof that no
reservation exists. No caller may treat this result as purchase authorization
without a provider-backed negative inventory assertion.
"""
from datetime import date

JOURNEY = ('Wien Meidling','Wiener Neustadt Hbf','18:22','18:49','1009','Comfort2+')
BLOCKING_LOCAL = frozenset(('PENDING','CONFIRMED','UNCERTAIN'))
PREFERRED = (('11','233A'),('11','233D'),('11','191D'),('11','182A'))
# Seat 193 is intentionally excluded until its coach/class is verified.

def final_booking_gate(day, connection, control, provider, local_status, selection,
                       provider_absence_verified=False):
    result={'status':'booking_blocked','date':day,'bookingAuthorized':False,
            'purchaseExecuted':False,'reason':'unverified_input'}
    try:
        date.fromisoformat(day)
        if not isinstance(connection,dict) or not isinstance(control,dict) or not isinstance(provider,dict):
            return result
        if local_status in BLOCKING_LOCAL:
            result['reason']='local_duplicate_or_uncertain'
            return result
        if local_status not in (None,'NONE'):
            result['reason']='unknown_local_state'
            return result
        if provider.get('found') is True:
            result['reason']='provider_reservation_exists'
            return result
        if provider.get('found') is not False or provider.get('diagnosis')!='not_exposed_in_checked_web_views':
            result['reason']='provider_evidence_ambiguous'
            return result
        if provider_absence_verified is not True:
            result['reason']='provider_absence_not_authoritative'
            return result
        expected={'date':day,'departure':'18:22','arrival':'18:49','trainNumber':'1009',
                  'displayedPriceCents':0,'priceSource':'comfort_control'}
        if any(connection.get(k)!=v for k,v in expected.items()):
            result['reason']='connection_or_price_mismatch'
            return result
        if control.get('bookingFieldState')!='enabled_zero_euro' or control.get('bookingFieldClickable') is not True:
            result['reason']='control_not_verified'
            return result
        if not isinstance(selection,dict) or (selection.get('coach'),selection.get('seat')) not in PREFERRED:
            result['reason']='seat_not_verified'
            return result
        # This preflight intentionally never authorizes or performs purchase.
        result['status']='preflight_verified'
        result['reason']='checkout_still_requires_independent_final_verification'
        return result
    except (ValueError,TypeError):
        return result
