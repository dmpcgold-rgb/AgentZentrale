#!/usr/bin/env python3
"""Read-only audit of WESTbahn's local single-attempt markers.

Never navigates, books, reads tickets or modifies the browser profile.
Marker presence means an attempt may have been sent, NOT ticket issuance.
"""
import json
import os
from pathlib import Path

def main():
    root=Path(os.environ.get("WESTBAHN_BROWSER_PROFILE","./data/westbahn-browser")).resolve()
    names={
      "originalApprovalAttempt":"approval_attempt_20261120.flag",
      "firstRecoveryApprovalAttempt":"approval_attempt_20261120_recovery1.flag",
      "secondRecoveryApprovalAttempt":"approval_attempt_20261120_recovery2.flag",
      "finalCheckoutRequestAttempt":"checkout_attempt_20261120.flag"
    }
    flags={label:(root/name).is_file() for label,name in names.items()}
    print(json.dumps({
      "status":"local_attempt_audit_only",
      "markers":flags,
      "anyApprovalMayHaveBeenSent":any(flags[k] for k in
        ("originalApprovalAttempt","firstRecoveryApprovalAttempt",
         "secondRecoveryApprovalAttempt")),
      "checkoutRequestMayHaveBeenSent":flags["finalCheckoutRequestAttempt"],
      "ticketIssuedVerified":False,
      "safeToRunNewPurchase":False,
      "note":"Markers are not proof of server-side ticket status"
    },ensure_ascii=False))
if __name__=="__main__":
    main()
