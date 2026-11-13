#!/usr/bin/env bash
# Isolated encryption/restore test. Never touches Oracle, Drive, or production keys.
set -Eeuo pipefail
umask 077
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/source/nested" "$tmp/restored"
printf 'agentzentrale-backup-roundtrip\n' > "$tmp/source/nested/state.txt"
printf 'test-key-only\n' > "$tmp/key"
printf 'incorrect-key\n' > "$tmp/wrong-key"
chmod 600 "$tmp/key" "$tmp/wrong-key"
tar -C "$tmp/source" -czf - . |
  gpg --batch --yes --no-tty --pinentry-mode loopback --passphrase-file "$tmp/key" --symmetric --cipher-algo AES256 --output "$tmp/archive.gpg"
test -s "$tmp/archive.gpg"
if gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$tmp/wrong-key" --decrypt "$tmp/archive.gpg" > /dev/null 2>&1; then
  echo 'ERROR: incorrect key decrypted archive' >&2
  exit 1
fi
gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$tmp/key" --decrypt "$tmp/archive.gpg" |
  tar -C "$tmp/restored" -xzf -
diff -r "$tmp/source" "$tmp/restored"
echo 'PASS: encrypted archive restored; wrong key rejected'
