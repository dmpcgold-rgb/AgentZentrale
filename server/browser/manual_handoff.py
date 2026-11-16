"""Fail-closed human handoff for WESTbahn reservations.

This module is pure: it does not open a browser, send requests, or buy tickets.
"""
from datetime import date

def manual_handoff(day, preparation, inventory=None):
    result={"status":"manual_review_required","date":day,
            "bookingAuthorized":False,"purchaseExecuted":False,
            "allowLiveRequests":False,
            "journey":{"origin":"Wien Meidling","destination":"Wiener Neustadt Hbf",
                       "departure":"18:22","class":"Comfort Class 2+"},
            "seatPriority":["233A","233D","191D","182A","193"],
            "excluded":["wheelchair_seats","four_seat_groups"],
            "nextAction":"Do not purchase; inspect account inventory and complete checkout manually only after verifying 0 EUR."}
    try:
        date.fromisoformat(day)
    except (ValueError,TypeError):
        result["status"]="blocked"
        result["reason"]="invalid_date"
        return result
    if not isinstance(preparation,dict) or preparation.get("accountVerifiedBeforeSearch") is not True:
        result["status"]="blocked"
        result["reason"]="account_unverified"
        return result
    if preparation.get("status")!="connection_found":
        result["status"]="blocked"
        result["reason"]="connection_not_verified"
        return result
    connection=preparation.get("connection")
    if not isinstance(connection,dict) or type(connection.get("displayedPriceCents")) is not int or connection["displayedPriceCents"]!=0:
        result["status"]="blocked"
        result["reason"]="zero_euro_not_verified"
        return result
    if connection.get("date")!=day or connection.get("departure")!="18:22":
        result["status"]="blocked"
        result["reason"]="journey_mismatch"
        return result
    if isinstance(inventory,dict) and inventory.get("potentialDuplicate"):
        result["status"]="blocked"
        result["reason"]="possible_existing_reservation"
        return result
    result["reason"]="provider_absence_not_authoritative"
    result["displayedPriceCents"]=0
    return result
