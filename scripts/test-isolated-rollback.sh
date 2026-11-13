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
