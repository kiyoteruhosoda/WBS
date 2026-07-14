#!/usr/bin/env bash
# WBS deploy script (stg / prod common). Place this repository's deploy bundle under
# wbs/<stg|prod>/ and run ./scripts/deploy.sh <app|migrate|reset> from that env directory.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
ENV_NAME="$(basename "$BASE_DIR")"

case "$ENV_NAME" in
  stg)
    PROJECT="wbs-stg"
    DEFAULT_WEB_HOST_PORT=8051
    ;;
  prod)
    PROJECT="wbs"
    DEFAULT_WEB_HOST_PORT=8050
    ;;
  *)
    echo "[deploy][error] このスクリプトは wbs/stg/scripts/ または wbs/prod/scripts/ に配置して実行してください。" >&2
    echo "  現在の配置: $SCRIPT_DIR（親ディレクトリ名 '$ENV_NAME' が stg / prod ではありません）" >&2
    exit 1
    ;;
esac

TAG="[deploy:$ENV_NAME]"
log()  { echo -e "\033[36m${TAG}\033[0m $*"; }
warn() { echo -e "\033[33m${TAG}[warn]\033[0m $*" >&2; }
err()  { echo -e "\033[31m${TAG}[error]\033[0m $*" >&2; }

IMAGE_TAR="$BASE_DIR/image.tar"
COMPOSE_FILE="$BASE_DIR/docker-compose.yml"
ENV_FILE="$BASE_DIR/.env"
IMAGE_VERSION_FILE="$BASE_DIR/.image-version"
SOURCE_TAG="$(cat "$IMAGE_VERSION_FILE" 2>/dev/null || echo local)"
API_IMAGE="wbs-api:$ENV_NAME"
WEB_IMAGE="wbs-web:$ENV_NAME"
SOURCE_API_IMAGE="wbs-api:$SOURCE_TAG"
SOURCE_WEB_IMAGE="wbs-web:$SOURCE_TAG"

MODE="${1:-}"
case "$MODE" in
  app|migrate|reset) ;;
  *)
    err "Mode required. Usage: $0 <app|migrate|reset>"
    exit 1
    ;;
esac

env_file_value() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d'=' -f2- \
    | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' || true
}

HOST_DATA_ROOT="$(env_file_value HOST_DATA_ROOT)"
HOST_DATA_ROOT="${HOST_DATA_ROOT:-$BASE_DIR/mnt}"
DATA_PATH="$HOST_DATA_ROOT/data"
WEB_HOST_PORT="$(env_file_value WEB_HOST_PORT)"
WEB_HOST_PORT="${WEB_HOST_PORT:-$DEFAULT_WEB_HOST_PORT}"
HEALTH_URL="$(env_file_value HEALTH_URL)"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${WEB_HOST_PORT}/api/health}"

export API_IMAGE WEB_IMAGE HOST_DATA_ROOT WEB_HOST_PORT
COMPOSE=(docker compose -p "$PROJECT" -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
ALL_SERVICES=(api web)

dump_module_logs() {
  echo "" >&2
  echo "----- diagnostics ($TAG) -----" >&2
  echo "$TAG container status:" >&2
  "${COMPOSE[@]}" ps -a >&2 || true
  local svc
  for svc in "$@"; do
    echo "" >&2
    echo "$TAG ---- module logs: $svc (last 100 lines) ----" >&2
    "${COMPOSE[@]}" logs --tail 100 --timestamps "$svc" >&2 || true
  done
  echo "------------------------------" >&2
}

fail() {
  local msg="$1"
  shift || true
  err "$msg"
  if [ $# -gt 0 ]; then
    dump_module_logs "$@"
  fi
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}

on_unexpected_error() {
  local line="$1"
  err "Unexpected error at line $line (mode: $MODE)"
  dump_module_logs "${ALL_SERVICES[@]}"
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
}
trap 'on_unexpected_error $LINENO' ERR

log "WBS deploy start (env: $ENV_NAME, mode: $MODE, base: $BASE_DIR)"

if ! docker info >/dev/null 2>&1; then
  err "Cannot reach the Docker daemon (permission denied or daemon down)."
  echo "  Run this script with sudo, or add your user to the 'docker' group and re-login:" >&2
  echo "    sudo $0 $MODE" >&2
  exit 1
fi

log "Mount root: $HOST_DATA_ROOT"

load_image_with_progress() {
  local tar="$1"
  local size_human
  size_human="$(du -h "$tar" 2>/dev/null | cut -f1)"
  log "Loading image: $tar (${size_human:-unknown size})"

  if command -v pv >/dev/null 2>&1; then
    pv "$tar" | docker load
    return
  fi

  log "(tip: install 'pv' to show docker load progress)"
  docker load -i "$tar" &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 5
    waited=$((waited + 5))
    if kill -0 "$pid" 2>/dev/null; then
      log "...still loading, ${waited}s elapsed (pid $pid) - this is normal for large images"
    fi
  done
  if ! wait "$pid"; then
    fail "docker load failed for $tar"
  fi
}

retag_for_env() {
  local loaded="$1" target="$2"
  if ! docker tag "$loaded" "$target"; then
    fail "Failed to tag $loaded as $target"
  fi
  log "Tagged $loaded -> $target"
}

if [ -f "$IMAGE_TAR" ]; then
  load_image_with_progress "$IMAGE_TAR"
  retag_for_env "$SOURCE_API_IMAGE" "$API_IMAGE"
  retag_for_env "$SOURCE_WEB_IMAGE" "$WEB_IMAGE"
elif docker image inspect "$API_IMAGE" >/dev/null 2>&1 && docker image inspect "$WEB_IMAGE" >/dev/null 2>&1; then
  warn "Image tar not found: $IMAGE_TAR — reusing already-loaded $API_IMAGE / $WEB_IMAGE"
else
  err "Image tar not found: $IMAGE_TAR"
  echo "  ビルドマシンで './scripts/build.sh --app-version <tag>' を実行し、dist/deploy/image.tar を $IMAGE_TAR へ配置してください。" >&2
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "No docker-compose.yml found at $COMPOSE_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
  warn "$ENV_FILE not found; generating a default template."
  mkdir -p "$BASE_DIR"
  cat > "$ENV_FILE" <<ENVEOF
# Auto-generated WBS deploy env (env: $ENV_NAME).
# Defaults are development-grade. Override before exposing externally.
HOST_DATA_ROOT=$BASE_DIR/mnt
WEB_HOST_PORT=$WEB_HOST_PORT
# DATABASE_URL=sqlite:////app/data/app.db
# ADMIN_EMAIL=local@example.com
# ADMIN_PASSWORD=change-me-strong
# HEALTH_URL=http://127.0.0.1:$WEB_HOST_PORT/api/health
ENVEOF
fi

log "Ensuring host mount root exists: $HOST_DATA_ROOT"
mkdir -p "$DATA_PATH" || fail "Could not create host data path: $DATA_PATH"

log "docker compose down"
"${COMPOSE[@]}" down || true

if [ "$MODE" = "reset" ]; then
  echo -e "\033[33m[reset] WARNING: This will delete all $ENV_NAME WBS data.\033[0m"
  echo "[reset] Deleting $DATA_PATH"
  rm -rf "$DATA_PATH"
  mkdir -p "$DATA_PATH"
fi

log "docker compose up -d"
UP_OUTPUT="$(mktemp)"
if ! "${COMPOSE[@]}" up -d --remove-orphans 2>&1 | tee "$UP_OUTPUT"; then
  err "docker compose up failed"
  echo "" >&2
  echo "$TAG ---- 'docker compose up' output ----" >&2
  cat "$UP_OUTPUT" >&2
  rm -f "$UP_OUTPUT"
  dump_module_logs "${ALL_SERVICES[@]}"
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
fi
rm -f "$UP_OUTPUT"

run_migrations_with_retry() {
  local attempt
  for attempt in 1 2 3; do
    if "${COMPOSE[@]}" exec -T api python scripts/run_db_migrations.py; then
      return 0
    fi
    warn "DB migration failed (attempt $attempt/3); retrying in 5s"
    sleep 5
  done
  fail "DB migration failed after 3 attempts" api
}

case "$MODE" in
  migrate|reset)
    log "Applying DB schema sync"
    run_migrations_with_retry
    ;;
esac

log "Waiting for service health: $HEALTH_URL"
for i in $(seq 1 60); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    log "Service healthy"
    break
  fi
  log "...waiting ($i/60)"
  sleep 2
done

if ! curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
  err "Health check failed: $HEALTH_URL"
  dump_module_logs api web
  echo "" >&2
  echo "$TAG next commands:" >&2
  echo "  docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE logs -f api" >&2
  echo "  docker compose -p $PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE logs -f web" >&2
  err "Deploy failed (mode: $MODE, env: $ENV_NAME)"
  exit 1
fi

log "Cleaning old unused Docker images"
docker image prune -f >/dev/null 2>&1 || true

echo -e "\033[32m${TAG} Deploy complete (mode: $MODE)\033[0m"
