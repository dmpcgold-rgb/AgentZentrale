#!/usr/bin/env bash
# Inventory and protected snapshot only; no checkout actions or deployment.
set -Eeuo pipefail
mode="${1:-}"
if [[ "$mode" != "--inventory" && "$mode" != "--snapshot" ]]; then
  echo "Usage: oracle-source-inventory.sh --inventory|--snapshot" >&2; exit 64
fi
[[ "$(id -u)" == 0 ]] || { echo "STOP: sudo root access required" >&2; exit 2; }
cd /opt/agentzentrale
git_safe() { git -c safe.directory=/opt/agentzentrale "$@"; }
[[ "$(git_safe rev-parse --show-toplevel)" == "$PWD" ]] || { echo "Unexpected repository root" >&2; exit 2; }
echo "Oracle repository inspection (filenames only; no source or secrets)"
python3 - <<'PY'
import subprocess
items=subprocess.check_output(['git','-c','safe.directory=/opt/agentzentrale',
 'status','--porcelain=v1','-z','--untracked-files=all']).split(b'\x00')
allowed=('server/browser/','server/tests/','scripts/','docs/', '.github/workflows/')
safe_exact=('compose.yaml','Dockerfile','package.json','.gitignore')
visible=0
suppressed=0
i=0
while i < len(items):
    raw=items[i]; i+=1
    if not raw: continue
    status=raw[:2].decode('ascii','replace')
    path=raw[3:].decode('utf-8','replace')
    if status[0] in 'RC' or status[1] in 'RC':
        i+=1   # -z rename/copy has second path
    sensitive=any(s in path.lower() for s in ('secret','token','.env','credential',
        'password','cookie','profile','ledger','ticket','backup','.key','.pem'))
    allowed_path=path.startswith(allowed) or path in safe_exact
    if allowed_path and not sensitive and visible < 50:
        print(f"  {status} {path}")
        visible+=1
    else:
        suppressed+=1
print(f"VISIBLE_SAFE_PATHS={visible}")
print(f"REDACTED_OR_OTHER_PATHS={suppressed}")
print("Note: modified checkout files may be excluded by the sensitive-path filter.")
PY
cid="$(docker compose -f /opt/agentzentrale/compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] || { echo "STOP: AgentZentrale container not running" >&2; exit 2; }
for f in ticketshop_station_dry_run.py checkout_20261123.py checkout_20261124.py checkout_20261125.py checkout_20261126.py checkout_20261127.py; do
  if docker exec "$cid" test -f "/app/server/browser/$f"; then
    echo "CONTAINER_PYTHON_PRESENT: $f"
  else
    echo "CONTAINER_PYTHON_MISSING: $f"
  fi
done
if [[ "$mode" == "--inventory" ]]; then
  echo "INVENTORY COMPLETE: Read-only."
  exit 0
fi
umask 077
parent=/root/agentzentrale-private-snapshots
install -d -m 700 "$parent"
target="$(mktemp -d "$parent/snapshot-XXXXXXXX")"
install -d -m 700 "$target/container-browser" "$target/oracle-worktree"
count=0
for f in ticketshop_station_dry_run.py checkout_20261123.py checkout_20261124.py checkout_20261125.py checkout_20261126.py checkout_20261127.py; do
  if docker exec "$cid" test -f "/app/server/browser/$f"; then
    docker cp "$cid:/app/server/browser/$f" "$target/container-browser/$f"
    chmod 600 "$target/container-browser/$f"
    count=$((count+1))
  fi
done
if [[ -f /opt/agentzentrale/server/browser/ticketshop_station_dry_run.py ]]; then
  cp -- /opt/agentzentrale/server/browser/ticketshop_station_dry_run.py "$target/oracle-worktree/ticketshop_station_dry_run.py"
  chmod 600 "$target/oracle-worktree/ticketshop_station_dry_run.py"
fi
[[ "$count" -ge 1 ]] || { echo "No checkout source copied"; exit 3; }
echo "PRIVATE SNAPSHOT COMPLETE: $count container checkout files; stored only on Oracle."
echo "SNAPSHOT_DIRECTORY=$target"
echo "No checkout was executed; no Git commit or deployment occurred."
