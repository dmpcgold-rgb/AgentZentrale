#!/usr/bin/env bash
# Local encrypted backup. Install and schedule only after configuring the key.
set -Eeuo pipefail
umask 077

ROOT=/opt/agentzentrale
BACKUP_DIR=/var/backups/agentzentrale
KEY_FILE=/etc/agentzentrale/backup-passphrase
COMPOSE="$ROOT/compose.yaml"
LOCK=/var/lock/agentzentrale-backup.lock

exec 9>"$LOCK"
flock -n 9 || { echo "Backup already running"; exit 1; }
test "$(id -u)" -eq 0 || { echo "Run as root"; exit 1; }
command -v gpg >/dev/null || { echo "Install gnupg first"; exit 1; }
command -v python3 >/dev/null || { echo "Install python3 for backup verification"; exit 1; }
command -v docker >/dev/null || { echo "Install docker first"; exit 1; }
test -r "$COMPOSE" || { echo "Missing compose file: $COMPOSE"; exit 1; }
test -r "$ROOT/scripts/verify-backup-archive.sh" || { echo "Missing backup verifier"; exit 1; }
test -r "$ROOT/scripts/check-backup-tar.py" || { echo "Missing tar safety validator"; exit 1; }
test -s "$KEY_FILE" || { echo "Missing backup passphrase file: $KEY_FILE"; exit 1; }
test "$(stat -c %a "$KEY_FILE")" = 600 || { echo "Key file must have permissions 600"; exit 1; }

container=$(docker compose -f "$COMPOSE" ps -q agentzentrale)
test -n "$container" || { echo "AgentZentrale container not found"; exit 1; }
test "$(docker inspect -f '{{.State.Running}}' "$container")" = true || { echo "Container not running"; exit 1; }

install -d -m 700 "$BACKUP_DIR"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
target="$BACKUP_DIR/agentzentrale-$timestamp.tar.gz.gpg"
temp=$(mktemp "$BACKUP_DIR/.backup.XXXXXXXX")
trap 'rm -f "$temp"' EXIT

# Encrypt the tar stream immediately; never store a plaintext archive on disk.
# An online snapshot may not be transactionally consistent for active browser files.
docker exec "$container" tar -C /app/server/data -czf - . |
  gpg --batch --yes --no-tty --pinentry-mode loopback --passphrase-file "$KEY_FILE" \
    --symmetric --cipher-algo AES256 --output "$temp"

test -s "$temp"
# Validate the encrypted archive and reject unsafe paths and link entries.
# Fail closed: do not publish or prune backups if validation fails.
bash "$ROOT/scripts/verify-backup-archive.sh" "$temp" "$KEY_FILE"
mv -- "$temp" "$target"
chmod 600 "$target"
trap - EXIT

# Only prune after a verified, successful backup.
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'agentzentrale-*.tar.gz.gpg' -mtime +13 -delete
echo "Encrypted backup verified: $target"
