#!/usr/bin/env bash
# Read-only verification of the latest protected Oracle source snapshot.
set -Eeuo pipefail
[[ "${1:-}" == "--audit" ]] || { echo 'Usage: --audit' >&2; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: sudo root required' >&2; exit 2; }
umask 077
parent=/root/agentzentrale-private-snapshots
[[ -d "$parent" ]] || { echo 'STOP: no backup directory on Oracle'; exit 3; }
snapshot="$(find "$parent" -mindepth 1 -maxdepth 1 -type d -name 'reconcile-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$snapshot" && -f "$snapshot/source/oracle-worktree.tgz" && -f "$snapshot/SHA256SUMS" ]] || { echo 'STOP: complete reconcile snapshot missing'; exit 3; }
(cd "$snapshot" && sha256sum -c --quiet SHA256SUMS) || { echo 'STOP: snapshot checksum mismatch'; exit 4; }
python3 - "$snapshot" <<'PY'
import ast, pathlib, sys, tarfile, hashlib
p=pathlib.Path(sys.argv[1])
checkout=sorted((p/'container-browser').glob('*.py'))
count=0
for file in checkout:
    ast.parse(file.read_text(encoding='utf-8'), filename=file.name)
    count+=1
assert count == 6, f'expected 6 checkout source files; got {count}'
py_count=0
names=set()
with tarfile.open(p/'source/oracle-worktree.tgz', 'r:gz') as archive:
    for item in archive:
        if not item.isfile():
            continue
        if item.name.startswith('/') or '..' in pathlib.PurePosixPath(item.name).parts:
            raise ValueError('unsafe archive entry')
        names.add(item.name)
        if item.name.endswith('.py'):
            file=archive.extractfile(item)
            ast.parse(file.read().decode('utf-8'), filename='archived/'+item.name)
            py_count+=1
print('SNAPSHOT_CHECKSUMS=OK')
print('CHECKOUT_PYTHON_SYNTAX=OK')
print('CHECKOUT_SOURCE_FILES='+str(count))
print('ARCHIVED_PYTHON_SYNTAX=OK')
print('ARCHIVED_PYTHON_FILES='+str(py_count))
print('ARCHIVED_DISTINCT_FILES='+str(len(names)))
PY
cid="$(docker compose -f /opt/agentzentrale/compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] || { echo 'STOP: live container missing'; exit 5; }
live_mismatch=0
compared=0
tmp="$(mktemp -d "$parent/livecheck-XXXXXXXX")"
trap 'rm -rf "$tmp"' EXIT
for file in "$snapshot"/container-browser/*.py; do
  base="${file##*/}"
  if ! docker cp "$cid:/app/server/browser/$base" "$tmp/$base" >/dev/null 2>&1; then
    live_mismatch=$((live_mismatch+1))
  elif ! cmp -s "$file" "$tmp/$base"; then
    live_mismatch=$((live_mismatch+1))
  fi
  compared=$((compared+1))
done
printf 'LIVE_SOURCE_COMPARED=%s\n' "$compared"
printf 'LIVE_SOURCE_DIFFERENCES=%s\n' "$live_mismatch"
cd /opt/agentzentrale
dirty="$(git -c safe.directory=/opt/agentzentrale status --porcelain -z --untracked-files=all | tr -cd '\0' | wc -c)"
printf 'ORACLE_GIT_DIRTY_ENTRIES=%s\n' "$dirty"
if [[ "$live_mismatch" -gt 0 ]]; then
  echo 'AUDIT_COMPLETE_WITH_DIFFERENCES: live checkout changed after archive; do not deploy.'
else
  echo 'AUDIT_COMPLETE: checksum and syntax verified; production unchanged.'
fi
echo 'NO_BOOKINGS_EXECUTED=yes'
echo 'NO_DEPLOYMENT_EXECUTED=yes'
echo 'NO_PRIVATE_SOURCE_UPLOADED=yes'
echo 'APPLY_STILL_BLOCKED=yes'
