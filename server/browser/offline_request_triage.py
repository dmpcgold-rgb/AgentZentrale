#!/usr/bin/env python3
"""Offline, fail-closed triage of sanitized WESTbahn seat network diagnostics.

Never authorizes requests, seats, bookings, or purchases. Accepts only the
redacted JSON emitted by worker.py seat-network-diagnostic.
"""
import json
import sys

def provider_host(host):
    """Match the exact WESTbahn domain or a dot-delimited subdomain only."""
    if not isinstance(host, str):
        return False
    host = host.lower()
    return any(host == domain or host.endswith("." + domain)
               for domain in ("westbahn.at", "westbahn.de"))


def triage(report):
    blocked = report.get("blockedRequests", [])
    if report.get("status") != "seat_network_diagnostic" or not isinstance(blocked, list):
        return {"status": "invalid_diagnostic", "bookingAuthorized": False, "allowLiveRequests": False}
    groups = {"read_candidate": [], "write_risk": [], "unknown": []}
    for item in blocked:
        if not isinstance(item, dict):
            groups["unknown"].append({"method": "UNKNOWN", "host": "redacted", "path": "/:redacted"})
            continue
        method = str(item.get("method", "")).upper()
        path = str(item.get("path", ""))
        host = str(item.get("host", ""))
        # Only provider-host metadata may be considered for read-only triage.
        # This is classification, never permission to send a request.
        segments = set(path.lower().split("/"))
        writes = {"booking", "bookings", "reservation", "reservations", "checkout",
                  "cart", "basket", "order", "orders", "payment", "payments",
                  "purchase", "confirm", "confirmation", "add", "remove", "update"}
        reads = {"availability", "seatmap", "seat-map", "layout", "layouts", "search", "offers"}
        if method not in ("GET", "HEAD", "POST") or segments & writes:
            category = "write_risk"
        elif (method in ("GET", "HEAD") and provider_host(host)
              and segments & reads and ":redacted" not in path):
            category = "read_candidate"
        else:
            category = "unknown"
        groups[category].append({"method": method, "host": host, "path": path})
    return {"status": "offline_request_triage", "counts": {k: len(v) for k,v in groups.items()},
            "requests": groups, "requiresProviderContractReview": bool(groups["unknown"] or groups["write_risk"]),
            "bookingAuthorized": False, "allowLiveRequests": False,
            "liveAvailabilityVerified": False,
            "reason": "sanitized URL and HTTP method cannot prove POST is read-only"}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(triage(payload), ensure_ascii=False))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"status": "invalid_diagnostic", "bookingAuthorized": False,
                          "allowLiveRequests": False, "error": type(exc).__name__}))
        sys.exit(1)
