#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="$SCRIPT_DIR/docker/docker-compose.yml"
HOST_HOME=${HOME:?HOME must be set}
ACTION=${1:-status}

usage() {
  printf '%s\n' "Usage: installer/context_mcp.sh [up|build|rebuild|refresh|restart|stop|down|status|logs]"
}

case "$ACTION" in
  up|build|rebuild|refresh|restart|stop|down|status|logs) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || {
  printf '%s\n' "Docker is required to manage core-context." >&2
  exit 1
}
docker compose version >/dev/null 2>&1 || {
  printf '%s\n' "Docker Compose v2 is required to manage core-context." >&2
  exit 1
}

compose() {
  HOST_HOME="$HOST_HOME" docker compose \
    -f "$COMPOSE_FILE" \
    "$@"
}

wait_until_ready() {
  attempts=0
  while [ "$attempts" -lt 90 ]; do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' \
      core-context-mcp 2>/dev/null || true)
    if [ "$status" = healthy ]; then
      printf '%s\n' "core-context is ready at http://127.0.0.1:8989/mcp"
      return 0
    fi
    if [ "$status" = unhealthy ] || [ "$status" = exited ]; then
      compose logs --tail 100 >&2
      printf '%s\n' "core-context failed its readiness check." >&2
      return 1
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  compose logs --tail 100 >&2
  printf '%s\n' "Timed out waiting for core-context readiness." >&2
  return 1
}

case "$ACTION" in
  up)
    compose up --build --detach
    wait_until_ready
    ;;
  build)
    compose build
    ;;
  rebuild)
    compose up --build --force-recreate --detach
    wait_until_ready
    ;;
  refresh)
    compose up --no-build --force-recreate --detach
    wait_until_ready
    ;;
  restart)
    compose restart
    wait_until_ready
    ;;
  stop) compose stop ;;
  down) compose down ;;
  status) compose ps ;;
  logs) compose logs --follow ;;
esac
