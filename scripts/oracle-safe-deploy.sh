#!/usr/bin/env bash
# Safe deploy of the EXISTING Oracle AgentZentrale. Never wipe production checkout state.
set -Eeuo pipefail
cd /opt/agentzentrale
if [[ "${1:-}" != "--apply" && "${1:-}" != "--check" ]]; then
  echo "Usage: oracle-safe-deploy.sh --check|--apply" >&2; exit 64
fi
if [[ "$(git rev-parse --show-toplevel)" != "$PWD" ]]; then
  echo "STOP: /opt/agentzentrale is not the Git worktree root" >&2; exit 2
fi
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "STOP: Server contains local changes/untracked files. Nothing will be overwritten."
  echo "Back up and reconcile the Oracle-only checkout code before deploying." >&2
  exit 2
fi
# This checkout was previously installed with docker cp; rebuilding would erase it.
# Require checkout source to be version-controlled BEFORE any container replacement.
for file in server/browser/ticketshop_station_dry_run.py server/browser/worker.py; do
  if ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    echo "STOP: Checkout source is not tracked in Git: $file" >&2
    echo "Rebuilding would remove live Oracle-only changes. No deployment performed." >&2
    exit 2
  fi
done
if [[ "${1}" == "--check" ]]; then
  echo "PREFLIGHT OK: Clean server tree and tracked checkout. No changes made."
  exit 0
fi
# Recheck against updated repository state before replacing the image.
git fetch --no-tags origin main
git merge --ff-only origin/main
docker compose -f compose.yaml config -q
docker compose -f compose.yaml build agentzentrale
docker compose -f compose.yaml up -d --no-deps agentzentrale
docker compose -f compose.yaml ps agentzentrale
echo "DEPLOY COMPLETE: Check application and booking logs separately."
