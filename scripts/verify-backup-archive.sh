#!/usr/bin/env bash
# Read-only disaster-recovery check for an existing encrypted backup.
# Usage: bash scripts/verify-backup-archive.sh /path/archive.tar.gz.gpg /path/passphrase
# Does not extract files, modify services, upload data, or delete backups.
set -Eeuo pipefail
umask 077
if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 ARCHIVE_GPG PASSPHRASE_FILE" >&2
  exit 2
fi
archive="$1"
key="$2"
test -f "$archive" && test -s "$archive" || { echo "Missing or empty encrypted archive" >&2; exit 1; }
test -f "$key" && test -s "$key" || { echo "Missing or empty passphrase file" >&2; exit 1; }
[[ "$(stat -c %a "$key")" == 600 ]] || { echo "Passphrase file must have mode 600" >&2; exit 1; }
command -v gpg >/dev/null
command -v tar >/dev/null
# Stream decrypted bytes into gzip/tar validation, never write plaintext to disk.
gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$key" --decrypt "$archive" |
  tar -tzf - >/dev/null
echo "PASS: encrypted archive decrypts and its tar/gzip stream validates (no extraction)"
