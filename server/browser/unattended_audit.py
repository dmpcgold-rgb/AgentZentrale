"""Unattended, read-only WESTbahn commuter audit.

No seat selection, checkout, or purchase API is called here.
Run via the existing container's Python interpreter.
"""
import argparse
from datetime import date, timedelta
import json
import subprocess
import sys
from pathlib import Path

WORKER = Path(__file__).with_name("worker.py")
VERIFIED = {"detail_verified", "visible_year_verified"}

def weekdays(start, count=5):
    if not 1 <= count <= 5:
        raise ValueError("invalid_count")
    result = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result

def safe_summary(payload, requested):
    """Whitelist fields; never print tickets, references, tokens or raw browser errors."""
    if not isinstance(payload, dict) or payload.get("status") != "inventory_batch_read":
        return {"status":"audit_blocked","dates":requested,"bookingAuthorized":False,
                "purchaseExecuted":False,"reason":"inventory_unavailable"}
    items = payload.get("days")
    if not isinstance(items, list) or len(items) != len(requested):
        return {"status":"audit_blocked","dates":requested,"bookingAuthorized":False,
                "purchaseExecuted":False,"reason":"invalid_inventory_response"}
    seen = set()
    results = []
    for item in items:
        if not isinstance(item, dict) or item.get("date") not in requested or item["date"] in seen:
            return {"status":"audit_blocked","dates":requested,"bookingAuthorized":False,
                    "purchaseExecuted":False,"reason":"invalid_inventory_response"}
        seen.add(item["date"])
        # inventory_batch emits detailVerified/dateVerified, not bookingReferenceChecked.
        # An explicitly dated visible card is a conflict even without full detail proof.
        verified = (item.get("status")=="detail_verified" and
                    item.get("dateVerified") is True and
                    item.get("detailVerified") is True)
        visible_conflict = (item.get("status") in ("visible_year_verified","possible_existing") or
                            item.get("potentialDuplicate") is True or
                            bool(item.get("seats")))
        results.append({"date":item["date"],"status":"existing_verified" if verified else "possible_existing" if visible_conflict else "needs_review",
                        "seats":[seat for seat in item.get("seats",[]) if isinstance(seat,str)
                                 and len(seat)<=5][:3] if (verified or visible_conflict) else []})
    return {"status":"audit_completed","days":sorted(results,key=lambda x:x["date"]),
            "bookingAuthorized":False,"purchaseExecuted":False,
            "message":"Automatische Bestandsprüfung abgeschlossen. Buchung bleibt gesperrt, solange fehlende Reservierungen nicht autoritativ ausgeschlossen werden können."}

def inspect_unbooked_days(summary, worker=WORKER, timeout=90):
    """Read-only fare inspection for uncertain days; no seat or checkout clicks."""
    if summary.get("status")!="audit_completed":
        return summary
    inspected=[]
    for item in summary["days"]:
        if item["status"]!="needs_review":
            inspected.append({**item,"fareInspection":"not_needed"})
            continue
        try:
            proc=subprocess.run([sys.executable,str(worker),"comfort-inspect",
                                 "--date",item["date"]],capture_output=True,text=True,
                                timeout=timeout,check=False)
            payload=json.loads(proc.stdout.strip()) if proc.returncode==0 else {}
            connection=payload.get("connection") if isinstance(payload,dict) else None
            # Zero-euro observation is never a booking authorization.
            verified=(isinstance(connection,dict) and
                      connection.get("displayedPriceCents") == 0 and
                      type(connection.get("displayedPriceCents")) is int and
                      payload.get("accountVerifiedBeforeSearch") is True and
                      payload.get("bookingAuthorized") is False and
                      payload.get("date") == item["date"] and
                      payload.get("status") in ("comfort_inspected","comfort_inspect"))
            inspected.append({**item,"fareInspection":"zero_euro_observed" if verified
                              else "unverified"})
        except (subprocess.TimeoutExpired,ValueError,OSError):
            inspected.append({**item,"fareInspection":"unavailable"})
    return {**summary,"days":inspected,"bookingAuthorized":False,"purchaseExecuted":False,
            "nextAction":"manual_verification_required",
            "reason":"provider_inventory_and_checkout_not_authoritative"}

def run(start, worker=WORKER, timeout=240, inspect_fares=False):
    dates = weekdays(start)
    try:
        result = subprocess.run([sys.executable,str(worker),"inventory-batch","--dates",",".join(dates)],
                                capture_output=True,text=True,timeout=timeout,check=False)
        if result.returncode:
            return {"status":"audit_blocked","dates":dates,"bookingAuthorized":False,
                    "purchaseExecuted":False,"reason":"worker_failed"}
        payload = json.loads(result.stdout.strip())
        summary=safe_summary(payload,dates)
        return inspect_unbooked_days(summary,worker) if inspect_fares else summary
    except (subprocess.TimeoutExpired,ValueError,OSError):
        return {"status":"audit_blocked","dates":dates,"bookingAuthorized":False,
                "purchaseExecuted":False,"reason":"worker_unavailable"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",help="ISO start date (default: today)")
    parser.add_argument("--inspect-fares",action="store_true",help="Read-only Comfort fare inspection for missing dates")
    args=parser.parse_args()
    try:
        start=date.fromisoformat(args.start) if args.start else date.today()
        result=run(start,inspect_fares=args.inspect_fares)
    except ValueError:
        result={"status":"audit_blocked","reason":"invalid_start_date",
                "bookingAuthorized":False,"purchaseExecuted":False}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result["status"]=="audit_completed" else 2

if __name__=="__main__":
    raise SystemExit(main())
