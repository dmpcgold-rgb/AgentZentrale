"""Read-only WESTbahn trip plan. No seat clicks or booking actions."""
from datetime import date

SEATS=("233A","233D","191D","182A","193")
def plan(day,prepared):
    date.fromisoformat(day)
    result={"status":"review_required","date":day,
            "route":{"origin":"Wien Meidling","destination":"Wiener Neustadt Hbf",
                     "departure":"18:22","class":"Comfort Class 2+"},
            "preferredSeats":list(SEATS),
            "seatRules":{"excludeWheelchair":True,"excludeFourSeatGroups":True},
            "bookingAuthorized":False,"purchaseExecuted":False,
            "seatAvailabilityVerified":False,
            "nextAction":"Review actual seat map and checkout manually; do not purchase automatically."}
    if not isinstance(prepared,dict) or prepared.get("accountVerifiedBeforeSearch") is not True:
        result["reason"]="account_unverified"
        return result
    if prepared.get("status")!="connection_found":
        result["reason"]="connection_not_verified"
        return result
    connection=prepared.get("connection")
    if not isinstance(connection,dict):
        result["reason"]="connection_not_verified"
        return result
    if connection.get("date")!=day or connection.get("departure")!="18:22":
        result["reason"]="journey_mismatch"
        return result
    price=connection.get("displayedPriceCents")
    if type(price) is not int or price!=0:
        result["reason"]="zero_euro_not_verified"
        return result
    result["status"]="ready_for_manual_seat_review"
    result["reason"]="seat_availability_not_verified"
    result["displayedPriceCents"]=0
    return result

def seat_review_summary(trip, seat_observation=None):
    """Combine trip readiness and independently observed seat data without guessing."""
    result={"status":"review_required","bookingAuthorized":False,
            "purchaseExecuted":False,"seatConfirmed":False,
            "preferredSeats":list(SEATS),"selectedSeat":None,
            "nextAction":"Verify actual Comfort seat map and checkout manually."}
    if not isinstance(trip,dict) or trip.get("status")!="ready_for_manual_seat_review":
        result["reason"]="trip_not_ready"
        return result
    if not isinstance(seat_observation,dict) or seat_observation.get("verified") is not True:
        result["reason"]="seat_map_unverified"
        return result
    seat=seat_observation.get("seat")
    if seat not in SEATS or seat_observation.get("comfortClassVerified") is not True:
        result["reason"]="seat_or_class_unverified"
        return result
    if seat_observation.get("wheelchair") is not False or seat_observation.get("fourSeatGroup") is not False:
        result["reason"]="seat_layout_unverified"
        return result
    result["selectedSeat"]=seat
    result["seatConfirmed"]=True
    result["status"]="ready_for_manual_checkout_review"
    result["reason"]="checkout_requires_manual_confirmation"
    return result
