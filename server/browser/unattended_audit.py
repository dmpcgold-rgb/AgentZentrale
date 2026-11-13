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
        verified = item.get("status") in VERIFIED and item.get("dateVerified") is True
        results.append({"date":item["date"],"status":"existing_visible" if verified else "needs_review",
                        "seats":[seat for seat in item.get("seats",[]) if isinstance(seat,str)
                                 and len(seat)<=5][:3] if verified else []})
    return {"status":"audit_completed","days":sorted(results,key=lambda x:x["date"]),
            "bookingAuthorized":False,"purchaseExecuted":False,
            "message":"Automatische Bestandsprüfung abgeschlossen. Buchung bleibt gesperrt, solange fehlende Reservierungen nicht autoritativ ausgeschlossen werden können."}

def run(start, worker=WORKER, timeout=240):
    dates = weekdays(start)
    try:
        result = subprocess.run([sys.executable,str(worker),"inventory-batch","--dates",",".join(dates)],
                                capture_output=True,text=True,timeout=timeout,check=False)
        if result.returncode:
            return {"status":"audit_blocked","dates":dates,"bookingAuthorized":False,
                    "purchaseExecuted":False,"reason":"worker_failed"}
        payload = json.loads(result.stdout.strip())
        return safe_summary(payload,dates)
    except (subprocess.TimeoutExpired,ValueError,OSError):
        return {"status":"audit_blocked","dates":dates,"bookingAuthorized":False,
                "purchaseExecuted":False,"reason":"worker_unavailable"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--start",help="ISO start date (default: today)")
    args=parser.parse_args()
    try:
        start=date.fromisoformat(args.start) if args.start else date.today()
        result=run(start)
    except ValueError:
        result={"status":"audit_blocked","reason":"invalid_start_date",
                "bookingAuthorized":False,"purchaseExecuted":False}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result["status"]=="audit_completed" else 2

if __name__=="__main__":
    raise SystemExit(main())
