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
    # Separate provider requests from other origins without exposing hostnames,
    # payloads, query strings or any unverified endpoint semantics.
    groups = {"provider": [], "other_origin": []}
    for row in rows:
        host = str(row["host"] or "").lower()
        provider = host in ("westbahn.at", "westbahn.de") or host.endswith((".westbahn.at", ".westbahn.de"))
        group = "provider" if provider else "other_origin"
        groups[group].append(row["index"])
    origin_summary = {
        group: {"count": len(indices), "requestIndices": indices,
                "contractVerified": False, "liveRequestPermitted": False}
        for group, indices in groups.items()
    }
    counts = dict(Counter(row["risk"] for row in rows))
    return {"status": "contract_review_required",
            "requestCount": len(rows),
            "originSummary": origin_summary,
            "requests": rows,
            "riskCounts": counts,
            "nextStep": "Verify endpoint semantics against provider documentation or authorized read-only evidence; never infer safety from HTTP method or URL alone.",
            "allowLiveRequests": False,
            "bookingAuthorized": False,
            "purchaseExecuted": False}

def main():
    """Review a previously captured, sanitized diagnostic from stdin only."""
    import json
    import sys
    # Bounded input and no network, browser, filesystem writes or execution.
    raw = sys.stdin.read(131073)
    if len(raw) > 131072:
        result = {"status": "review_blocked", "reason": "input_too_large",
                  "allowLiveRequests": False, "bookingAuthorized": False}
    else:
        try:
            result = review(json.loads(raw))
        except (ValueError, TypeError):
            result = {"status": "review_blocked", "reason": "invalid_json",
                      "allowLiveRequests": False, "bookingAuthorized": False}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
