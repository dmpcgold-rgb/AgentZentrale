#!/usr/bin/env bash
# Protected reconciliation archive. Production checkout and bookings are never touched.
set -Eeuo pipefail
[[ "${1:-}" == "--reconcile" ]] || { echo 'Usage: --reconcile' >&2; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: sudo root required' >&2; exit 2; }
cd /opt/agentzentrale
safe_git() { git -c safe.directory=/opt/agentzentrale "$@"; }
[[ "$(safe_git rev-parse --show-toplevel)" == "$PWD" ]] || { echo 'STOP: unexpected Git root' >&2; exit 2; }
umask 077
parent=/root/agentzentrale-private-snapshots
install -d -m 700 "$parent"
target="$(mktemp -d "$parent/reconcile-XXXXXXXX")"
install -d -m 700 "$target/container-browser" "$target/source"
# Archive the current version-controlled and visible untracked source (not ignored .env/profile).
python3 - "$target" <<'PY'
import os, pathlib, subprocess, sys
out=pathlib.Path(sys.argv[1])
raw=subprocess.check_output(['git','-c','safe.directory=/opt/agentzentrale',
 'ls-files','-co','--exclude-standard','-z'])
paths=sorted(set(p for p in raw.split(b'\0') if p and os.path.lexists(os.fsdecode(p))))
with open(out/'source-files.nul','wb') as fh:
    for p in paths:
        if p.startswith(b'/') or b'..' in p.split(b'/'):
            raise RuntimeError('unsafe path in repository')
        fh.write(p+b'\0')
(out/'source-count').write_text(str(len(paths)))
PY
tar --null --verbatim-files-from -czf "$target/source/oracle-worktree.tgz" -T "$target/source-files.nul"
chmod 600 "$target/source/oracle-worktree.tgz" "$target/source-files.nul"
cid="$(docker compose -f /opt/agentzentrale/compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] || { echo 'STOP: running container not found (archive preserved)' >&2; exit 3; }
count=0
for file in ticketshop_station_dry_run.py checkout_20261123.py checkout_20261124.py checkout_20261125.py checkout_20261126.py checkout_20261127.py; do
    if docker exec "$cid" test -f "/app/server/browser/$file"; then
        docker cp "$cid:/app/server/browser/$file" "$target/container-browser/$file" >/dev/null
        chmod 600 "$target/container-browser/$file"
        count=$((count+1))
    fi
done
[[ "$count" -gt 0 ]] || { echo 'STOP: no container checkout source found' >&2; exit 4; }
(cd "$target" && sha256sum source/oracle-worktree.tgz container-browser/*.py > SHA256SUMS)
chmod 600 "$target/SHA256SUMS"
printf 'PRIVATE_RECONCILE_COMPLETE\n'
printf 'SOURCE_FILES_ARCHIVED=%s\n' "$(cat "$target/source-count")"
printf 'TRACKED_CHANGES=%s\n' "$(safe_git status --porcelain -uno | wc -l)"
printf 'UNTRACKED_FILES=%s\n' "$(safe_git ls-files -o --exclude-standard | wc -l)"
printf 'CONTAINER_CHECKOUT_FILES=%s\n' "$count"
printf 'PRIVATE_ARCHIVE_CREATED_ON_ORACLE_ONLY=yes\nLIVE_CONTAINER_RESTARTED=no\nPRODUCTION_FILES_MODIFIED=no\nDEPLOY_STILL_GUARDED=yes\n'
