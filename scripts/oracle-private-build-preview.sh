#!/usr/bin/env bash
# Build and verify a candidate image from Oracle's PRIVATE staged source.
# Never create/replace a running container. Never upload logs or source.
set -Eeuo pipefail
[[ "${1:-}" == "--preview" ]] || { echo 'PREVIEW_BLOCKED=invalid_mode'; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'PREVIEW_BLOCKED=requires_root'; exit 2; }
umask 077
stage_root=/root/agentzentrale-private-staging
[[ -d "$stage_root" ]] || { echo 'PREVIEW_BLOCKED=staging_missing'; exit 3; }
latest="$(find "$stage_root" -mindepth 1 -maxdepth 1 -type d -name 'source-*' -printf '%T@ %p\n' | sort -nr | head -n 1 | cut -d' ' -f2-)"
[[ -n "$latest" && -f "$latest/code/Dockerfile" && -f "$latest/code/compose.yaml" ]] || { echo 'PREVIEW_BLOCKED=stage_source_missing'; exit 3; }
[[ -f "$latest/code/server/browser/ticketshop_station_dry_run.py" ]] || { echo 'PREVIEW_BLOCKED=checkout_missing'; exit 3; }
for day in 23 24 25 26 27; do
 [[ -f "$latest/code/server/browser/checkout_202611$day.py" ]] || { echo 'PREVIEW_BLOCKED=dated_checkout_missing'; exit 3; }
done
if [[ "$(docker compose -f /opt/agentzentrale/compose.yaml ps -q agentzentrale | wc -l)" -lt 1 ]]; then
 echo 'PREVIEW_BLOCKED=production_container_missing'; exit 3
fi
# Validate source checkout without Python-generated __pycache__ in the staging tree.
python3 - "$latest/code" <<'PY'
import ast, pathlib, sys
root=pathlib.Path(sys.argv[1])
for p in root.joinpath('server/browser').glob('checkout_202611*.py'):
    ast.parse(p.read_text(encoding='utf-8'), filename=p.name)
ast.parse((root/'server/browser/ticketshop_station_dry_run.py').read_text(encoding='utf-8'))
print("PREVIEW_CHECKOUT_SYNTAX=OK")
PY
# Verify the candidate Docker build does not receive historical runtime/session state.
for path in server/.env server/data .git; do
 [[ ! -e "$latest/code/$path" ]] || { echo 'PREVIEW_BLOCKED=runtime_or_git_data_present'; exit 4; }
done
log="$(mktemp /root/agentzentrale-private-snapshots/build-log-XXXXXXXX)"
chmod 600 "$log"
tag="agentzentrale-oracle-candidate:private-preview"
echo "PREVIEW_BUILD_STARTED=yes"
if docker build --pull=false --progress=plain --tag "$tag" "$latest/code" >"$log" 2>&1; then
 echo "PREVIEW_BUILD=OK"
 echo "PRIVATE_CANDIDATE_IMAGE_BUILT=yes"
 echo "LIVE_CONTAINER_RESTARTED=no"
 echo "PRODUCTION_FILES_MODIFIED=no"
 echo "NO_BOOKINGS_EXECUTED=yes"
 echo "NO_DEPLOYMENT_EXECUTED=yes"
 echo "NO_PRIVATE_SOURCE_UPLOADED=yes"
 echo "APPLY_STILL_BLOCKED=yes"
else
 echo "PREVIEW_BUILD=FAILED"
 echo "PREVIEW_BUILD_LOG_PRIVATE=yes"
 echo "LIVE_CONTAINER_RESTARTED=no"
 echo "NO_DEPLOYMENT_EXECUTED=yes"
 exit 5
fi
