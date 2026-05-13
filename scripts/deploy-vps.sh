#!/bin/bash
# Rolling deploy for PicUr on the VPS. Recreates one frontend instance at a
# time so nginx (which fronts both via ip_hash + proxy_next_upstream failover)
# always has a healthy upstream to route to. Backend/worker/retention can be
# deployed alongside; only the frontend pair needs the staggered recreate.
#
# Usage (run on the VPS, in /opt/ahgir):
#   ./scripts/deploy-vps.sh                # frontend + backend + worker + retention
#   ./scripts/deploy-vps.sh frontend-only  # only roll the two frontend instances
#
# Idempotent: safe to re-run. Exits non-zero if either frontend fails health check.

set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.vps.yml"
MODE="${1:-full}"

wait_healthy() {
    local port="$1"
    local name="$2"
    for i in $(seq 1 30); do
        if curl -fs "http://127.0.0.1:${port}/" -o /dev/null; then
            echo "  ✓ ${name} healthy on :${port}"
            return 0
        fi
        sleep 1
    done
    echo "  ✗ ${name} failed to come up on :${port} within 30s"
    docker logs --tail 40 "${name}" || true
    return 1
}

echo "==> Pulling latest"
git pull --ff-only

# Clean any hash-prefixed ghost containers left over from failed recreates.
# Docker uses these names like "<id>_picur-<svc>" when the desired name is
# stuck on a half-removed container; if we don't sweep them up, every later
# recreate fails with "container <id> is not running" until manually removed.
echo "==> Sweeping stale hash-prefixed picur containers"
GHOSTS="$(docker ps -a --format '{{.Names}}' | grep -E '^[0-9a-f]+_picur-' || true)"
if [ -n "$GHOSTS" ]; then
    echo "$GHOSTS" | xargs -r docker rm -f
fi

if [ "$MODE" = "full" ]; then
    echo "==> Building backend / worker / frontend images"
    $COMPOSE build backend worker frontend
    echo "==> Recreating backend / worker / retention-scheduler"
    $COMPOSE up -d --no-deps --force-recreate backend worker retention-scheduler
else
    # frontend-only: only rebuild the frontend image. Touching backend/worker
    # images here would force a recreate even though we don't want one.
    echo "==> Building frontend image"
    $COMPOSE build frontend
    # Make sure backend/worker/retention are running, but don't rebuild or
    # recreate them. up -d is a no-op when an image hasn't changed.
    echo "==> Ensuring backend / worker / retention-scheduler are running"
    $COMPOSE up -d --no-deps backend worker retention-scheduler
fi

echo "==> Rolling frontend (instance 2 first, then instance 1)"
$COMPOSE up -d --no-deps --force-recreate frontend-2
wait_healthy 3002 picur-frontend-2

$COMPOSE up -d --no-deps --force-recreate frontend
wait_healthy 3001 picur-frontend

echo "==> Final container status"
docker ps --filter name=picur --format 'table {{.Names}}\t{{.Status}}'

echo "==> Done."
