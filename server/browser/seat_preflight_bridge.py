"""Bridge verified seat-picker state to the fail-closed final booking gate.

This module never clicks a browser control, submits a basket or purchases.
A seat label alone is not proof of selection or availability.
"""
from final_booking_gate import final_booking_gate

def inspect_selected_seat(day, connection, control, provider, local_status,
                          seat_modal, detail_summary, provider_absence_verified=False):
    """Evaluate only evidence read from the actual seat modal and detail page."""
    selection=None
    if isinstance(seat_modal,dict) and isinstance(detail_summary,dict):
        selected=seat_modal.get('selected')
        if (seat_modal.get('modalFound') is True
            and isinstance(selected,dict)
            and seat_modal.get('activeCoach')==selected.get('coach')
            and (seat_modal.get('comfortMap') is True or seat_modal.get('detailComfort') is True)
            and detail_summary.get('verified') is True
            and detail_summary.get('date')==day
            and detail_summary.get('displayedPriceCents')==0):
            selection=selected
    result=final_booking_gate(day,connection,control,provider,local_status,
                              selection,provider_absence_verified)
    result['seatSelectionVerified']=selection is not None and result.get('reason')!='seat_not_verified'
    result['bookingAuthorized']=False
    result['purchaseExecuted']=False
    return result
