#!/usr/bin/env bash
# Isolated integration test: no Oracle SSH, secrets, or production volumes.
set -euo pipefail
name="agentzentrale-rollback-test-$$"
tmp="$(mktemp -d)"
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  rm -rf "$tmp"
}
trap cleanup EXIT

cat > "$tmp/Dockerfile" <<'DOCKER'
FROM node:22-alpine
ARG MODE=healthy
ENV MODE=$MODE
HEALTHCHECK --interval=1s --timeout=1s --start-period=1s --retries=2 CMD node -e "process.exit(process.env.MODE === 'healthy' ? 0 : 1)"
CMD ["node", "-e", "setInterval(() => {}, 1000)"]
DOCKER

docker build -q --build-arg MODE=healthy -t "$name:healthy" "$tmp" >/dev/null
docker build -q --build-arg MODE=broken -t "$name:broken" "$tmp" >/dev/null

wait_health() {
  local expected="$1" state
  for i in $(seq 1 25); do
    state="$(docker inspect --format '{{.State.Health.Status}}' "$name")"
    if [[ "$state" == "$expected" ]]; then return 0; fi
    sleep 1
  done
  echo "Expected $expected, got $state" >&2
  return 1
}

docker run -d --name "$name" "$name:healthy" >/dev/null
wait_health healthy
docker rm -f "$name" >/dev/null

docker run -d --name "$name" "$name:broken" >/dev/null
wait_health unhealthy
docker rm -f "$name" >/dev/null

# Simulate the production rollback decision by restoring the prior image.
docker run -d --name "$name" "$name:healthy" >/dev/null
wait_health healthy
echo "PASS: healthy -> unhealthy -> restored healthy (isolated Docker test)"

# Also exercise Git and Docker Compose rollback in a separate temporary repository.
# No remote, credentials, ports, or production volumes are used.
compose_tmp="$(mktemp -d)"
compose_project="az-rollback-$$"
cleanup_compose() {
  docker compose -p "$compose_project" -f "$compose_tmp/compose.yaml" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$compose_tmp"
}
trap 'cleanup_compose; cleanup' EXIT
cd "$compose_tmp"
git init -q -b main
git config user.name "CI Rollback Test"
git config user.email "ci@example.invalid"
cp "$tmp/Dockerfile" ./Dockerfile
cat > compose.yaml <<'COMPOSE'
services:
  agentzentrale:
    build:
      context: .
      args:
        MODE: ${MODE:-healthy}
    image: agentzentrale-rollback-integration-test
COMPOSE
printf 'MODE=healthy\n' > .env
git add Dockerfile compose.yaml .env
git commit -qm "healthy version"
previous="$(git rev-parse HEAD)"
docker compose -p "$compose_project" up -d --build --wait --wait-timeout 90
printf 'MODE=broken\n' > .env
git add .env
git commit -qm "broken version"
docker compose -p "$compose_project" up -d --build --force-recreate
cid="$(docker compose -p "$compose_project" ps -q agentzentrale)"
test -n "$cid"
unhealthy=0
for i in $(seq 1 30); do
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$cid")"
  if [[ "$state" == unhealthy ]]; then unhealthy=1; break; fi
  sleep 1
done
test "$unhealthy" -eq 1 || { echo "Broken Compose version never became unhealthy" >&2; exit 1; }
git checkout -q -B main "$previous"
docker compose -p "$compose_project" up -d --build --force-recreate --wait --wait-timeout 90
test "$(git rev-parse HEAD)" = "$previous"
restored="$(docker compose -p "$compose_project" ps -q agentzentrale)"
test -n "$restored"
test "$(docker inspect --format '{{.State.Health.Status}}' "$restored")" = healthy
echo "PASS: isolated Git and Docker Compose rollback"
