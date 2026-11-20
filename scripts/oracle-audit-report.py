#!/usr/bin/env python3
"""Create a public-safe GitHub Actions report from allowlisted Oracle status fields.

Do not include stdout, paths, filenames, secrets, ticket numbers, seat codes, or source code.
"""
import json
import os
import pathlib
import re
import sys

if len(sys.argv) != 4:
    raise SystemExit("usage: oracle-audit-report.py LOGFILE STATUSFILE REPORTFILE")
logfile, statusfile, reportfile = map(pathlib.Path, sys.argv[1:])
log = logfile.read_text(encoding="utf-8", errors="replace") if logfile.exists() else ""
exit_text = statusfile.read_text().strip() if statusfile.exists() else ""
exit_code = int(exit_text) if re.fullmatch(r"\d{1,3}", exit_text) else None

allowed_checks = {
    "SNAPSHOT_CHECKSUMS": ("OK",),
    "CHECKOUT_PYTHON_SYNTAX": ("OK",),
    "ARCHIVED_PYTHON_SYNTAX": ("OK",),
    "PRIVATE_ARCHIVE_CREATED_ON_ORACLE_ONLY": ("yes",),
    "LIVE_CONTAINER_RESTARTED": ("no",),
    "PRODUCTION_FILES_MODIFIED": ("no",),
    "NO_BOOKINGS_EXECUTED": ("yes",),
    "NO_DEPLOYMENT_EXECUTED": ("yes",),
    "NO_PRIVATE_SOURCE_UPLOADED": ("yes",),
    "APPLY_STILL_BLOCKED": ("yes",),
    "DEPLOY_STILL_GUARDED": ("yes",),
    "STAGED_SOURCE_ONLY_ON_ORACLE": ("yes",),
    "PREVIEW_CHECKOUT_SYNTAX": ("OK",),
    "PREVIEW_BUILD": ("OK",),
    "PRIVATE_CANDIDATE_IMAGE_BUILT": ("yes",),
}
allowed_counts = {
    "SOURCE_FILES_ARCHIVED", "TRACKED_CHANGES", "UNTRACKED_FILES",
    "CONTAINER_CHECKOUT_FILES", "CHECKOUT_SOURCE_FILES",
    "ARCHIVED_PYTHON_FILES", "ARCHIVED_DISTINCT_FILES",
    "LIVE_SOURCE_COMPARED", "LIVE_SOURCE_DIFFERENCES",
    "ORACLE_GIT_DIRTY_ENTRIES", "VISIBLE_SAFE_PATHS",
    "REDACTED_OR_OTHER_PATHS",
    "SOURCE_FILES_STAGED", "PRIVATE_PATHS_EXCLUDED",
    "CHECKOUT_FILES_STAGED", "PYTHON_FILES_VALIDATED",
}
values = {}
for line in log.splitlines():
    match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(\S+)", line.strip())
    if not match:
        continue
    key, value = match.groups()
    if key in allowed_checks and value in allowed_checks[key]:
        values[key] = value
    elif key in allowed_counts and re.fullmatch(r"\d{1,9}", value):
        values[key] = int(value)

mode = os.environ.get("MODE", "unknown")
if mode not in ("inventory", "snapshot", "reconcile", "audit", "stage", "preview", "check", "apply"):
    mode = "unknown"
markers = {
    "audit_complete": "AUDIT_COMPLETE:" in log,
    "private_stage_complete": "PRIVATE_STAGE_COMPLETE" in log,
    "audit_complete_with_differences": "AUDIT_COMPLETE_WITH_DIFFERENCES:" in log,
    "private_reconcile_complete": "PRIVATE_RECONCILE_COMPLETE" in log,
    "private_snapshot_complete": "PRIVATE SNAPSHOT COMPLETE" in log,
    "inventory_complete": "INVENTORY COMPLETE:" in log,
    "deploy_blocked": "DEPLOY BLOCKED" in log or "STOP: Unsafe deploy" in log,
    "deployment_reported_complete": "DEPLOY COMPLETE" in log,
}
report = {
    "schema_version": 1,
    "workflow_mode": mode,
    "remote_command_exit_code": exit_code,
    "status": "failed" if exit_code is None or exit_code != 0 else (
        "audit_verified" if mode == "audit" and markers["audit_complete"] and values.get("LIVE_SOURCE_DIFFERENCES") == 0 and
        values.get("SNAPSHOT_CHECKSUMS") == "OK" and values.get("CHECKOUT_PYTHON_SYNTAX") == "OK" else
        "stage_verified" if mode == "stage" and markers["private_stage_complete"] and values.get("STAGED_SOURCE_ONLY_ON_ORACLE") == "yes" and values.get("SNAPSHOT_CHECKSUMS") == "OK" and values.get("CHECKOUT_FILES_STAGED") == 6 and values.get("NO_DEPLOYMENT_EXECUTED") == "yes" else
        "preview_verified" if mode == "preview" and values.get("PREVIEW_BUILD") == "OK" and values.get("PREVIEW_CHECKOUT_SYNTAX") == "OK" and values.get("PRIVATE_CANDIDATE_IMAGE_BUILT") == "yes" and values.get("NO_DEPLOYMENT_EXECUTED") == "yes" else
        "audit_differences" if mode == "audit" and markers["audit_complete_with_differences"] else
        "completed_with_deploy_blocked" if markers["deploy_blocked"] else
        "completed_without_audit_verification"
    ),
    "checks": values,
    "markers": markers,
}
reportfile.parent.mkdir(parents=True, exist_ok=True)
reportfile.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("SANITIZED_REPORT_CREATED")
print(f"REPORT_STATUS={report['status']}")
