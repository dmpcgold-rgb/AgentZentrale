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
