"""Offline-only contract review for blocked WESTbahn seat-map requests.

No request is replayed, no credentials/payloads are stored, and no permission
to perform a live request or purchase is granted by this module.
"""
from collections import Counter

def review(diagnostic):
    if not isinstance(diagnostic, dict) or diagnostic.get("status") != "seat_network_diagnostic":
        return {"status": "review_blocked", "reason": "invalid_diagnostic",
                "allowLiveRequests": False, "bookingAuthorized": False}
    requests = diagnostic.get("blockedRequests")
    if not isinstance(requests, list):
        return {"status": "review_blocked", "reason": "missing_requests",
                "allowLiveRequests": False, "bookingAuthorized": False}
    allowed_keys = ("method", "host", "path", "resourceType",
                    "hasQuery", "isNavigationRequest", "hasBody")
    rows = []
    for index, item in enumerate(requests, 1):
        if not isinstance(item, dict):
            return {"status": "review_blocked", "reason": "malformed_request",
                    "allowLiveRequests": False, "bookingAuthorized": False}
        row = {key: item.get(key) for key in allowed_keys}
        row["index"] = index
        method = str(row["method"] or "").upper()
        path = str(row["path"] or "")
        host = str(row["host"] or "").lower()
        provider_host = host in ("westbahn.at", "westbahn.de") or host.endswith((".westbahn.at", ".westbahn.de"))
        row["contractStatus"] = "unverified"
        if method not in ("GET", "HEAD"):
            row["risk"] = "mutation_possible"
        elif not provider_host or ":redacted" in path:
            row["risk"] = "unknown"
        else:
            row["risk"] = "read_candidate_only"
        row["needsIndependentProviderEvidence"] = True
        rows.append(row)
    counts = dict(Counter(row["risk"] for row in rows))
    return {"status": "contract_review_required",
            "requestCount": len(rows),
            "requests": rows,
            "riskCounts": counts,
            "nextStep": "Verify endpoint semantics against provider documentation or authorized read-only evidence; never infer safety from HTTP method or URL alone.",
            "allowLiveRequests": False,
            "bookingAuthorized": False,
            "purchaseExecuted": False}
