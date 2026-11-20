#!/usr/bin/env bash
# Safe deploy of the EXISTING Oracle AgentZentrale. Never wipe checkout state.
set -Eeuo pipefail
if [[ "${1:-}" != "--apply" && "${1:-}" != "--check" ]]; then
  echo "Usage: oracle-safe-deploy.sh --check|--apply" >&2; exit 64
fi
# Root-owned Oracle checkout. No change to existing filesystem permissions.
if [[ "$EUID" -ne 0 ]]; then
  echo "STOP: Preflight requires noninteractive sudo to read the checkout." >&2; exit 2
fi
cd /opt/agentzentrale
git_safe() { git -c safe.directory=/opt/agentzentrale "$@"; }
if [[ "$(git_safe rev-parse --show-toplevel)" != "$PWD" ]]; then
  echo "STOP: Unexpected Git checkout path." >&2; exit 2
fi
dirty=0
if [[ -n "$(git_safe status --porcelain --untracked-files=all)" ]]; then
  dirty=1
  echo "BLOCKED: Oracle has local changes / untracked files. No data changed."
fi
missing=0
for file in server/browser/ticketshop_station_dry_run.py server/browser/worker.py; do
  if ! git_safe ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    missing=1
    echo "BLOCKED: Checkout source is not tracked in Git: $file"
  fi
done
if [[ "$1" == "--check" ]]; then
  if (( dirty || missing )); then
    echo "SSH SUCCESSFUL; DEPLOY BLOCKED to preserve the production checkout."
  else
    echo "PREFLIGHT OK; no changes made."
  fi
  exit 0
fi
if (( dirty || missing )); then
  echo "STOP: Unsafe deploy. Never reset/clean to bypass protection." >&2; exit 2
fi
git_safe fetch --no-tags origin main
git_safe merge --ff-only origin/main
docker compose -f compose.yaml config -q
docker compose -f compose.yaml build agentzentrale
docker compose -f compose.yaml up -d --no-deps agentzentrale
docker compose -f compose.yaml ps agentzentrale
echo "DEPLOY COMPLETE"
