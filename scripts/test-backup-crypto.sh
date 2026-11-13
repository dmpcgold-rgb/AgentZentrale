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
bash "$(dirname "$0")/verify-backup-archive.sh" "$tmp/archive.gpg" "$tmp/key"
if bash "$(dirname "$0")/verify-backup-archive.sh" "$tmp/archive.gpg" "$tmp/wrong-key" >/dev/null 2>&1; then
  echo 'ERROR: verifier accepted incorrect passphrase' >&2
  exit 1
fi
chmod 644 "$tmp/key"
if bash "$(dirname "$0")/verify-backup-archive.sh" "$tmp/archive.gpg" "$tmp/key" >/dev/null 2>&1; then
  echo 'ERROR: verifier accepted insecure key permissions' >&2
  exit 1
fi
chmod 600 "$tmp/key"
if gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$tmp/wrong-key" --decrypt "$tmp/archive.gpg" > /dev/null 2>&1; then
  echo 'ERROR: incorrect key decrypted archive' >&2
  exit 1
fi
gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$tmp/key" --decrypt "$tmp/archive.gpg" |
  tar -C "$tmp/restored" -xzf -
diff -r "$tmp/source" "$tmp/restored"
# Simulate a truncated cloud upload: decryption + archive validation must fail.
size="$(stat -c %s "$tmp/archive.gpg")"
head -c "$((size / 2))" "$tmp/archive.gpg" > "$tmp/truncated.gpg"
if bash "$(dirname "$0")/verify-backup-archive.sh" "$tmp/truncated.gpg" "$tmp/key" >/dev/null 2>&1; then
  echo 'ERROR: verification utility accepted truncated archive' >&2
  exit 1
fi
if (set -o pipefail; gpg --batch --quiet --no-tty --pinentry-mode loopback --passphrase-file "$tmp/key" --decrypt "$tmp/truncated.gpg" 2>/dev/null | tar -tzf - >/dev/null 2>&1); then
  echo 'ERROR: truncated archive passed verification' >&2
  exit 1
fi
# A malicious tar member must be rejected even when encryption is valid.
python3 - "$tmp/unsafe.tar.gz" <<'PY'
import io
import sys
import tarfile
with tarfile.open(sys.argv[1], "w:gz") as archive:
    payload = b"unsafe"
    entry = tarfile.TarInfo("../escape.txt")
    entry.size = len(payload)
    archive.addfile(entry, io.BytesIO(payload))
PY
gpg --batch --yes --no-tty --pinentry-mode loopback --passphrase-file "$tmp/key" --symmetric --cipher-algo AES256 --output "$tmp/unsafe.gpg" "$tmp/unsafe.tar.gz"
if bash "$(dirname "$0")/verify-backup-archive.sh" "$tmp/unsafe.gpg" "$tmp/key" >/dev/null 2>&1; then
  echo 'ERROR: unsafe tar path accepted' >&2
  exit 1
fi
echo 'PASS: encrypted archive restored; wrong key, truncated archive, and unsafe tar path rejected'
