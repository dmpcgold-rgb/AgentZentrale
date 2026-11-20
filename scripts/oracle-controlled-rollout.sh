#!/usr/bin/env bash
# One-shot, fail-closed Oracle deployment of the verified PRIVATE checkout image.
# NEVER reset Git, publish checkout source, delete the ledger or repeat a booking.
set -Eeuo pipefail
[[ "${1:-}" == "--rollout" ]] || { echo 'ROLLOUT=BLOCKED_INVALID_MODE'; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'ROLLOUT=BLOCKED_ROOT_REQUIRED'; exit 2; }
umask 077
install -d -m 700 /root/agentzentrale-private-rollouts
exec 9>/root/agentzentrale-private-rollouts/deploy.lock
flock -n 9 || { echo 'ROLLOUT=BLOCKED_CONCURRENT_UPDATE'; exit 3; }
cd /opt/agentzentrale
compose=/opt/agentzentrale/compose.yaml
running="$(docker compose -f "$compose" ps -q agentzentrale)"
[[ -n "$running" && "$(docker inspect -f '{{.State.Running}}' "$running")" == true ]] || {
  echo 'ROLLOUT=BLOCKED_PRODUCTION_NOT_RUNNING'; exit 3;
}
# Validate the exact candidate image AND production's persistent ledger/volume.
stage_root=/root/agentzentrale-private-staging
stage="$(find "$stage_root" -mindepth 1 -maxdepth 1 -type d -name 'source-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$stage" && -d "$stage/code" ]] || { echo 'ROLLOUT=BLOCKED_STAGE_MISSING'; exit 3; }
fingerprint="$(cd "$stage/code" && sha256sum Dockerfile server/browser/worker.py server/browser/ticketshop_station_dry_run.py server/browser/checkout_202611{23,24,25,26,27}.py | sha256sum | awk '{print $1}')"
candidate=agentzentrale-oracle-candidate:private-preview
docker image inspect "$candidate" >/dev/null 2>&1 || { echo 'ROLLOUT=BLOCKED_BUILD_NOT_PRESENT'; exit 3; }
label="$(docker image inspect --format '{{ index .Config.Labels "at.agentzentrale.private-stage-fingerprint" }}' "$candidate")"
[[ "$label" == "$fingerprint" ]] || { echo 'ROLLOUT=BLOCKED_BUILD_STALE'; exit 3; }
mount_type="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/server/data"}}{{.Type}}{{end}}{{end}}' "$running")"
[[ "$mount_type" == volume ]] || { echo 'ROLLOUT=BLOCKED_DATA_VOLUME_NOT_PERSISTENT'; exit 3; }
docker exec "$running" test -s /app/server/data/westbahn.json || { echo 'ROLLOUT=BLOCKED_LEDGER_NOT_FOUND'; exit 3; }

# Fail closed on any active, pending, or uncertain live checkout.
# Never interpret an interrupted purchase as a reason to retry it.
guard_dir="$(mktemp -d /root/agentzentrale-private-rollouts/preflight-XXXXXXXX)"
chmod 700 "$guard_dir"
docker cp "$running:/app/server/data/westbahn.json" "$guard_dir/westbahn.json" >/dev/null
chmod 600 "$guard_dir/westbahn.json"
python3 - "$guard_dir/westbahn.json" <<'PY'
import json,sys
with open(sys.argv[1], encoding='utf-8') as fh: data=json.load(fh)
if not isinstance(data,dict) or not isinstance(data.get('rows'),dict):
    print('ROLLOUT=BLOCKED_LEDGER_SCHEMA'); sys.exit(3)
last=data.get('lastRun') or {}
if not isinstance(last,dict) or last.get('status')=='running':
    print('ROLLOUT=BLOCKED_BOOKING_RUNNING'); sys.exit(3)
for row in data['rows'].values():
    if not isinstance(row,dict) or row.get('status')=='booking':
        print('ROLLOUT=BLOCKED_PENDING_CHECKOUT'); sys.exit(3)
print('ROLLOUT_LEDGER_IDLE=YES')
PY
# Detect in-flight Playwright/checkout jobs. A read-only node server is expected.
# Docker's default process format is more portable than "-eo args" on
# Oracle host builds. Never let a failed inspection silently authorize rollout.
if ! docker top "$running" >"$guard_dir/live-processes" 2>/dev/null; then
  echo 'ROLLOUT=BLOCKED_PROCESS_INSPECTION_FAILED'; exit 3
fi
# Reject unexpected output instead of interpreting an empty/unsupported
# process listing as idle. Never print process arguments to Actions logs.
if ! head -n 1 "$guard_dir/live-processes" | grep -Eiq '(^|[[:space:]])(CMD|COMMAND|ARGS)([[:space:]]|$)' ||
   ! tail -n +2 "$guard_dir/live-processes" | grep -Eq '[[:space:]]node([[:space:]]|$)|node[[:space:]].*index[.]mjs'; then
  echo 'ROLLOUT=BLOCKED_PROCESS_LIST_UNVERIFIED'; exit 3
fi
if grep -Ei '(^|[ /])(checkout_202611[0-9]+[.]py|ticketshop_station_dry_run[.]py|worker[.]py|chromium|chrome|playwright)([[:space:]]|$)' "$guard_dir/live-processes" >/dev/null; then
  echo 'ROLLOUT=BLOCKED_BROWSER_WORK_ACTIVE'; exit 3
fi
# Old container's untracked docker-cp checkout code is preserved in the rollback image.
run="$(mktemp -d /root/agentzentrale-private-rollouts/release-XXXXXXXX)"
chmod 700 "$run"
cp -p -- "$guard_dir/westbahn.json" "$run/ledger-before.json"
rollback_tag="agentzentrale-oracle-rollback:$(basename "$run" | tr '[:upper:]' '[:lower:]')"
if ! docker commit --pause=true "$running" "$rollback_tag" >"$run/old-image-id"; then
  echo 'ROLLOUT=BLOCKED_ROLLBACK_IMAGE_FAILED'; exit 4
fi
chmod 600 "$run/old-image-id"
rollout_tag="agentzentrale-oracle-promoted:$(basename "$run" | tr '[:upper:]' '[:lower:]')"
docker tag "$candidate" "$rollout_tag"
cat > "$run/candidate.override.yaml" <<EOF
services:
  agentzentrale:
    image: $rollout_tag
EOF
cat > "$run/rollback.override.yaml" <<EOF
services:
  agentzentrale:
    image: $rollback_tag
EOF
chmod 600 "$run/"*.override.yaml
dc() { docker compose --project-directory /opt/agentzentrale -f "$compose" -f "$1" "${@:2}"; }
dc "$run/candidate.override.yaml" config -q || { echo 'ROLLOUT=BLOCKED_COMPOSE_INVALID'; exit 4; }
dc "$run/rollback.override.yaml" config -q || { echo 'ROLLOUT=BLOCKED_ROLLBACK_CONFIG_INVALID'; exit 4; }
[[ ! -e /opt/agentzentrale/compose.override.yaml ]] || { echo 'ROLLOUT=BLOCKED_EXISTING_COMPOSE_OVERRIDE'; exit 4; }

health_ok() {
  local override="$1" target="$2" new_id state
  for i in $(seq 1 36); do
    new_id="$(dc "$override" ps -q agentzentrale 2>/dev/null || true)"
    if [[ -n "$new_id" ]]; then
      state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$new_id" 2>/dev/null || true)"
      if [[ "$state" == healthy ]]; then
        docker exec "$new_id" test -s /app/server/data/westbahn.json || return 1
        [[ "$(docker inspect -f '{{.Image}}' "$new_id")" == "$target" ]] || return 1
        return 0
      fi
      [[ "$state" == unhealthy || "$state" == missing ]] && return 1
    fi
    sleep 5
  done
  return 1
}
rolled_out=0
rollback_needed=0
rollback() {
  if [[ "$rollback_needed" != 1 ]]; then return; fi
  set +e
  echo 'ROLLOUT=ROLLBACK_ATTEMPTED'
  dc "$run/rollback.override.yaml" up -d --no-deps --no-build --force-recreate agentzentrale >"$run/rollback.log" 2>&1
  rollback_status=$?
  old_id="$(docker image inspect -f '{{.Id}}' "$rollback_tag" 2>/dev/null)"
  if [[ "$rollback_status" == 0 ]] && health_ok "$run/rollback.override.yaml" "$old_id"; then
    echo 'ROLLOUT=ROLLED_BACK_TO_OLD_CONTAINER'
  else
    echo 'ROLLOUT=ROLLBACK_REQUIRES_MANUAL_RECOVERY'
  fi
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
new_image_id="$(docker image inspect -f '{{.Id}}' "$rollout_tag")"
rollback_needed=1
if ! dc "$run/candidate.override.yaml" up -d --no-deps --no-build --force-recreate agentzentrale >"$run/deploy.log" 2>&1; then
  echo 'ROLLOUT=NEW_CONTAINER_START_FAILED'; exit 5
fi
if ! health_ok "$run/candidate.override.yaml" "$new_image_id"; then
  echo 'ROLLOUT=NEW_CONTAINER_HEALTH_FAILED'; exit 5
fi
# Use a permanent override for ordinary docker compose commands, but preserve
# the private rollback image and the previous ledger snapshot on Oracle.
cp "$run/candidate.override.yaml" /opt/agentzentrale/compose.override.yaml
chmod 600 /opt/agentzentrale/compose.override.yaml
rollback_needed=0
trap - EXIT
echo 'ROLLOUT=SUCCESS'
echo 'PRODUCTION_CANDIDATE_RUNNING=yes'
echo 'ROLLBACK_IMAGE_SAVED_ON_ORACLE=yes'
echo 'LEDGER_VOLUME_PRESERVED=yes'
echo 'NO_BOOKINGS_EXECUTED=yes'
echo 'NO_PRIVATE_SOURCE_UPLOADED=yes'
