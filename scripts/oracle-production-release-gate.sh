#!/usr/bin/env bash
# Read-only production readiness gate. Never deploy or execute a checkout.
set -Eeuo pipefail
[[ "${1:-}" == "--release-check" ]] || { echo 'RELEASE_GATE=BLOCKED_INVALID_MODE'; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'RELEASE_GATE=BLOCKED_REQUIRES_ROOT'; exit 2; }
umask 077
cd /opt/agentzentrale
live="$(docker compose -f compose.yaml ps -q agentzentrale)"
[[ -n "$live" ]] || { echo 'RELEASE_GATE=BLOCKED_NO_LIVE_CONTAINER'; exit 3; }
running="$(docker inspect -f '{{.State.Running}}' "$live")"
[[ "$running" == true ]] || { echo 'RELEASE_GATE=BLOCKED_LIVE_CONTAINER_DOWN'; exit 3; }
image=agentzentrale-oracle-candidate:private-preview
docker image inspect "$image" >/dev/null 2>&1 || { echo 'RELEASE_GATE=BLOCKED_CANDIDATE_NOT_BUILT'; exit 3; }
stage_root=/root/agentzentrale-private-staging
stage="$(find "$stage_root" -mindepth 1 -maxdepth 1 -type d -name 'source-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$stage" && -d "$stage/code" ]] || { echo 'RELEASE_GATE=BLOCKED_STAGING_MISSING'; exit 3; }
fingerprint="$(cd "$stage/code" && sha256sum Dockerfile server/browser/worker.py server/browser/ticketshop_station_dry_run.py server/browser/checkout_202611{23,24,25,26,27}.py | sha256sum | awk '{print $1}')"
label="$(docker image inspect --format '{{ index .Config.Labels "at.agentzentrale.private-stage-fingerprint" }}' "$image")"
[[ "$label" == "$fingerprint" ]] || { echo 'RELEASE_GATE=BLOCKED_IMAGE_STALE'; exit 3; }
# Production booking state must remain backed by the named /app/server/data volume.
mount_type="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/server/data"}}{{.Type}}{{end}}{{end}}' "$live")"
[[ "$mount_type" == volume ]] || { echo 'RELEASE_GATE=BLOCKED_DATA_NOT_PERSISTENT'; exit 3; }
docker exec "$live" test -f /app/server/data/westbahn.json || { echo 'RELEASE_GATE=BLOCKED_LEDGER_MISSING'; exit 3; }
# A green check does not prove that the system is idle or that an in-flight purchase
# can be safely interrupted. Deployment requires separate release authorization.
echo 'RELEASE_GATE=READY_FOR_CONTROLLED_ROLLOUT'
echo 'CANDIDATE_MATCHES_PRIVATE_STAGE=yes'
echo 'LIVE_DATA_VOLUME_PERSISTENT=yes'
echo 'NO_BOOKINGS_EXECUTED=yes'
echo 'NO_DEPLOYMENT_EXECUTED=yes'
echo 'LIVE_CONTAINER_RESTARTED=no'
echo 'APPLY_STILL_BLOCKED=yes'
