#!/usr/bin/env bash
# Read-only operational audit; no credentials, booking changes or restarts.
set -euo pipefail
export LC_ALL=C
D=/opt/agentzentrale
C=agentzentrale-agentzentrale-1
fail=0
check() { if "$@" >/dev/null 2>&1; then echo "PASS: $*"; else echo "WARN: $*"; fail=1; fi; }
check systemctl is-active docker
check systemctl is-active westbahn-booking.timer
check systemctl is-active westbahn-recovery.timer
check systemctl is-active agentzentrale-control.timer
check test -d "$D/persistent-backend"
check test -f "$D/compose.yaml"
echo '=== Container ==='
docker inspect "$C" --format 'state={{.State.Status}} restart={{.RestartCount}} image={{.Image}}' || fail=1
echo '=== Published ports ==='
docker port "$C" || fail=1
echo '=== Disk ==='
df -h "$D"
echo '=== Persistent module integrity ==='
for f in index.mjs oracle-control.mjs oracle-status.mjs oracle-report.mjs ticket_detail_view.py; do
  case "$f" in *.py) dest="/app/server/browser/$f";; *) dest="/app/server/$f";; esac
  if [ ! -f "$D/persistent-backend/$f" ]; then echo "WARN: missing host module $f"; fail=1; continue; fi
  host=$(sha256sum "$D/persistent-backend/$f" | cut -d' ' -f1)
  live=$(docker exec "$C" sha256sum "$dest" | cut -d' ' -f1) || { fail=1; continue; }
  if [ "$host" = "$live" ]; then echo "PASS: $f identical"; else echo "WARN: $f drift"; fail=1; fi
  if ! docker inspect "$C" --format '{{range .Mounts}}{{println .Destination .RW}}{{end}}' | grep -Fxq "$dest false"; then
    echo "WARN: $f not mounted read-only in running container"; fail=1
  fi
done
echo '=== Booking service (informational) ==='
systemctl show westbahn-booking.service -p ActiveState -p SubState -p Result
echo '=== Secret file permissions (no contents) ==='
if [ -f "$D/server/.env" ]; then
  mode=$(stat -c '%a' "$D/server/.env")
  echo "server/.env mode=$mode"
  case "$mode" in 600|400) ;; *) echo 'WARN: review secret file permissions'; fail=1;; esac
fi
echo "AUDIT_COMPLETE warnings=$fail"
exit "$fail"
