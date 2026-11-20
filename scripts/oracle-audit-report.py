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
    "CANDIDATE_MATCHES_PRIVATE_STAGE": ("yes",),
    "LIVE_DATA_VOLUME_PERSISTENT": ("yes",),
    "PRODUCTION_CANDIDATE_RUNNING": ("yes",),
    "ROLLBACK_IMAGE_SAVED_ON_ORACLE": ("yes",),
    "LEDGER_VOLUME_PRESERVED": ("yes",),
    "BOOKING_STAGE": ("READY",),
    "BUILD_MODULE_SYNTAX_ERROR": ("yes","no"),
    "BUILD_NODE_ERROR_MISSING_NAMED_EXPORT": ("yes","no"),
    "BUILD_NODE_ERROR_UNEXPECTED_TOKEN": ("yes","no"),
    "BUILD_NODE_ERROR_UNEXPECTED_IDENTIFIER": ("yes","no"),
    "BUILD_NODE_ERROR_INVALID_REGEXP": ("yes","no"),
    "BUILD_NODE_ERROR_MODULE_MISSING": ("yes","no"),
    "BUILD_NODE_ERROR_JS_ASSERTION": ("yes","no"),
    "BUILD_NODE_ERROR_JS_REFERENCE_ERROR": ("yes","no"),
    "BUILD_NODE_ERROR_JS_TYPE_ERROR": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_INDEX_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_WESTBAHN_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_GMAIL-AUDIT_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SRC_CORE_WESTBAHN_JS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_TESTS_WESTBAHN_TEST_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_TESTS_GMAIL-AUDIT_TEST_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_BOOKING-READINESS_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_TRIP-PREVIEW_MJS": ("yes","no"),
    "BUILD_NODE_PUBLIC_SERVER_WEEKLY-REVIEW_MJS": ("yes","no"),
    "BUILD_STAGE_NODE_PUBLIC_TESTS": ("yes","no"),
    "BUILD_STAGE_PYTHON_BROWSER_TESTS": ("yes","no"),
    "BUILD_STAGE_PYTHON_COMPILATION": ("yes","no"),
    "BUILD_STAGE_NPM_OR_NODE_SETUP": ("yes","no"),
    "BUILD_TAP_FAILURES_FOUND": ("yes","no"),
    "BUILD_CLASS_NODE_TEST_ASSERTION": ("yes","no"),
    "BUILD_CLASS_NODE_MODULE_LOAD": ("yes","no"),
    "BUILD_CLASS_NODE_SYNTAX": ("yes","no"),
    "BUILD_CLASS_PYTHON_TEST": ("yes","no"),
    "BUILD_CLASS_APT_INSTALL": ("yes","no"),
    "BUILD_CLASS_PIP_INSTALL": ("yes","no"),
    "BUILD_CLASS_DOCKER_BUILD_CONTEXT": ("yes","no"),
    "BUILD_CLASS_DOCKER_PERMISSION": ("yes","no"),
    "BUILD_CLASS_DOCKER_OUT_OF_MEMORY": ("yes","no"),
    "BOOKING_TESTS": ("PASS",),
    "BOOKING_LIVE_GATE_ENABLED": ("yes","no"),
    "BOOKING_ADAPTER_PRESENT": ("yes","no"),
    "BOOKING_GMAIL_CONFIGURED": ("yes","no"),
    "BOOKING_LEDGER_VALID": ("yes","no"),
    "BOOKING_SCHEDULE_ENABLED": ("yes","no"),
    "BOOKING_ACTIVE_RUN": ("yes","no"),
    "BOOKING_AMBIGUOUS_ROWS": ("yes","no"),
    "BOOKING_WEEKLY_SCHEDULER_PRESENT": ("yes","no"),
    "BOOKING_PREREQUISITES_READY": ("yes","no"),
    "BOOKING_ACTION_EXECUTED": ("no",),
    "NO_MANUAL_BOOKING_TRIGGERED": ("yes",),
}
allowed_counts = {
    "SOURCE_FILES_ARCHIVED", "TRACKED_CHANGES", "UNTRACKED_FILES",
    "CONTAINER_CHECKOUT_FILES", "CHECKOUT_SOURCE_FILES",
    "ARCHIVED_PYTHON_FILES", "ARCHIVED_DISTINCT_FILES",
    "LIVE_SOURCE_COMPARED", "LIVE_SOURCE_DIFFERENCES",
    "ORACLE_GIT_DIRTY_ENTRIES", "VISIBLE_SAFE_PATHS",
    "REDACTED_OR_OTHER_PATHS",
    "BUILD_FIRST_FAILED_TEST_INDEX", "BUILD_FAILED_TEST_COUNT",
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
if mode not in ("inventory", "snapshot", "reconcile", "audit", "stage", "preview", "verify", "release-check", "rollout", "booking-status", "booking-enable", "booking-update", "booking-diagnose", "check", "apply"):
    mode = "unknown"
markers = {
    "audit_complete": "AUDIT_COMPLETE:" in log,
    "booking_config_checked": "BOOKING_CONFIG_CHECK=COMPLETE" in log,
    "booking_build_diagnosed": "BUILD_DIAGNOSIS=COMPLETE" in log,
    "booking_automation_enabled": "BOOKING_ACTIVATION=ENABLED" in log,
    "release_ready": "RELEASE_GATE=READY_FOR_CONTROLLED_ROLLOUT" in log,
    "rollout_complete": "ROLLOUT=SUCCESS" in log,
    "rollout_rolled_back": "ROLLOUT=ROLLED_BACK_TO_OLD_CONTAINER" in log,
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
        "booking_build_diagnosed" if mode == "booking-diagnose" and markers["booking_build_diagnosed"] else
        "booking_update_deployed" if mode == "booking-update" and values.get("BOOKING_STAGE") == "READY" and values.get("BOOKING_TESTS") == "PASS" and markers["rollout_complete"] and markers["booking_config_checked"] else
        "booking_automation_enabled" if mode == "booking-enable" and markers["booking_automation_enabled"] and values.get("NO_MANUAL_BOOKING_TRIGGERED") == "yes" else
        "booking_prerequisites_ready" if mode == "booking-status" and markers["booking_config_checked"] and values.get("BOOKING_PREREQUISITES_READY") == "yes" and values.get("BOOKING_ACTION_EXECUTED") == "no" else
        "booking_config_incomplete" if mode == "booking-status" and markers["booking_config_checked"] and values.get("BOOKING_ACTION_EXECUTED") == "no" else
        "rollout_success" if mode == "rollout" and markers["rollout_complete"] and values.get("PRODUCTION_CANDIDATE_RUNNING") == "yes" and values.get("ROLLBACK_IMAGE_SAVED_ON_ORACLE") == "yes" and values.get("LEDGER_VOLUME_PRESERVED") == "yes" else
        "verify_ready" if mode == "verify" and values.get("PREVIEW_BUILD") == "OK" and values.get("PRIVATE_CANDIDATE_IMAGE_BUILT") == "yes" and markers["release_ready"] and values.get("CANDIDATE_MATCHES_PRIVATE_STAGE") == "yes" and values.get("LIVE_DATA_VOLUME_PERSISTENT") == "yes" and values.get("NO_DEPLOYMENT_EXECUTED") == "yes" else
        "release_ready" if mode == "release-check" and markers["release_ready"] and values.get("CANDIDATE_MATCHES_PRIVATE_STAGE") == "yes" and values.get("LIVE_DATA_VOLUME_PERSISTENT") == "yes" and values.get("NO_DEPLOYMENT_EXECUTED") == "yes" else
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
