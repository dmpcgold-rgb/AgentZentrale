"""Conservative reconciliation of provider inventory and local attempt state.

Never infer booking authorization from missing tickets or missing ledger rows.
"""
from booking_ledger import AttemptLedger

BLOCKED_PROVIDER = frozenset(('existing_verified','possible_existing','needs_review'))
BLOCKED_LOCAL = frozenset(('PENDING','CONFIRMED','UNCERTAIN'))


def reconcile_days(summary, ledger_path, journey_key):
    if not isinstance(summary,dict) or summary.get('status')!='audit_completed':
        return summary
    output=[]
    ledger=None
    try:
        if not ledger_path:
            raise ValueError('ledger_not_configured')
        ledger=AttemptLedger(ledger_path)
        for item in summary.get('days',[]):
            if not isinstance(item,dict) or item.get('status') not in BLOCKED_PROVIDER:
                raise ValueError('invalid_provider_evidence')
            local=ledger.status(journey_key,item['date'])
            if local in BLOCKED_LOCAL:
                reason='local_'+local.lower()
            elif item['status']=='existing_verified':
                reason='provider_ticket_verified'
            elif item['status']=='possible_existing':
                reason='provider_ticket_possible'
            else:
                reason='provider_absence_unverified'
            output.append({**item,'localAttemptStatus':local or 'NONE',
                           'bookingBlockReason':reason,
                           'safeToBook':False,'bookingAuthorized':False})
    except Exception:
        # An inaccessible or corrupt ledger cannot be treated as empty.
        return {**summary,'status':'audit_blocked','reason':'ledger_unavailable',
                'bookingAuthorized':False,'purchaseExecuted':False,
                'safeToBook':False,'nextAction':'manual_verification_required'}
    finally:
        if ledger is not None:
            ledger.close()
    return {**summary,'days':output,'bookingAuthorized':False,
            'purchaseExecuted':False,'safeToBook':False,
            'nextAction':'manual_verification_required'}
