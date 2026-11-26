#!/usr/bin/env bash
# Host configuration and reservation-state backup; deliberately excludes live browser profile and credentials.
set -euo pipefail
umask 077
D=/opt/agentzentrale
W="$D/westbahn-stable"
B="$D/security/backups"
install -d -m 700 "$B"
exec 8>"$B/.backup.lock"
flock -n 8 || { echo 'BACKUP: already running'; exit 0; }
exec 9>>"$W/auto_book.lock"
flock -n 9 || { echo 'BACKUP: booking busy; retry on next timer'; exit 0; }
state=$(systemctl show westbahn-booking.service -p ActiveState --value)
case "$state" in inactive|failed) ;; *) echo 'BACKUP: booking not idle'; exit 0;; esac
stamp=$(date -u +%Y%m%dT%H%M%SZ)
tmp=$(mktemp -d "$B/.stage.XXXXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
files=(compose.yaml)
for f in index.mjs oracle-control.mjs oracle-status.mjs oracle-report.mjs ticket_detail_view.py; do
  files+=("persistent-backend/$f")
done
for f in confirmed_reservations.json pending_reservations.json booking_config.json auto_book.py recovery_v10.sh recovery_attempts.json stop_booking.request; do
  if [ -f "$W/$f" ]; then files+=("westbahn-stable/$f"); fi
done
for f in confirmed_reservations.json pending_reservations.json booking_config.json; do
  test -f "$W/$f" || { echo "BACKUP: missing required state $f"; exit 1; }
done
# Only explicit paths; never follow symlinks or include .env, OAuth, browser profiles.
for f in "${files[@]}"; do
  test -f "$D/$f" && test ! -L "$D/$f" || { echo "BACKUP: invalid path $f"; exit 1; }
done
# Encryption recipient must be configured independently of this host.
recipient_file="$D/security/backup-recipient.txt"
test -s "$recipient_file" || { echo 'BACKUP: encryption recipient missing'; exit 1; }
command -v age >/dev/null
recipient=$(cat "$recipient_file")
[[ "$recipient" =~ ^age1[0-9a-z]+$ ]] || { echo 'BACKUP: invalid recipient'; exit 1; }
tar -C "$D" -czf "$tmp/host.tar.gz" -- "${files[@]}"
tar -tzf "$tmp/host.tar.gz" >/dev/null
age -r "$recipient" -o "$tmp/host.tar.gz.age" "$tmp/host.tar.gz"
test -s "$tmp/host.tar.gz.age"
name="host-$stamp.tar.gz.age"
(cd "$tmp"; mv host.tar.gz.age "$name"; sha256sum "$name" > "$name.sha256"; sha256sum -c "$name.sha256")
# Publish checksum first, then archive. No deletion before a new successful backup.
mv "$tmp/$name.sha256" "$B/$name.sha256"
mv "$tmp/$name" "$B/$name"
echo "BACKUP_CREATED $name"
# Retention is deliberately manual until a restore test and off-host copy are verified.
