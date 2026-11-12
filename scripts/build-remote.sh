#!/bin/bash
# Build -> extract -> deploy WBS from outside the dev container (on the deployment host).
#
# Flow:
#   BUILD  : inside the dev container, run git pull + ./scripts/build.sh --app-version <VERSION>,
#            producing the deploy bundle (image.tar / docker-compose.yml /
#            scripts/deploy.sh etc.) in dist/deploy/
#   PICK   : copy the whole deploy bundle into this directory with docker cp
#   DEPLOY : run ./scripts/deploy.sh <MODE> (docker load, retag, compose up and
#            health checks are done by deploy.sh)
#
# Place this script alone under wbs/stg/ or wbs/prod/ (no repository checkout
# needed). deploy.sh detects the environment (stg / prod) from the directory name.
# The copy on the host compares the repository HEAD after git pull with its version stamp
# and updates itself on mismatch (self-update). If the script body changed, it
# exits with RESTART REQUIRED (exit 2); run it again.
#
# Usage:
#   ./build-remote.sh [run] [MODE]
#     MODE=app     : normal deploy (default)
#     MODE=migrate : start the container + schema sync
#     MODE=reset   : delete the mounted SQLite data and rebuild (destructive)
#   The first argument is a slot for the Agent's args registration (e.g. "run"); its value is unused.
#
# Overridable via environment variables:
#   DEV_CONTAINER      dev container that runs the build (default: ubuntu-dev)
#   DEV_CONTAINER_USER user for docker exec (default: sshuser)
#   PROJECT_DIR        repository path inside the container (default: /work/project/wbs)
#   VERSION            image version (default: generated from the date and time)
#   BUILD_ARGS         extra arguments for build.sh (e.g. "--skip-tests")
set -euo pipefail

# The repository commit hash is stamped when distributed to the host (self-update).
# In the repository this file always stays unversioned.
BUILD_REMOTE_VERSION="unversioned"

PROJECT=wbs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE=${2:-app}
case "$MODE" in
    app|migrate|reset) ;;
    *)
        echo "Usage: $0 [run] [app|migrate|reset]" >&2
        echo "  MODE '$MODE' is invalid." >&2
        exit 1
        ;;
esac

DEV_CONTAINER=${DEV_CONTAINER:-ubuntu-dev}
DEV_CONTAINER_USER=${DEV_CONTAINER_USER:-sshuser}
PROJECT_DIR=${PROJECT_DIR:-/work/project/$PROJECT}
VERSION=${VERSION:-$(date -u +%Y.%m.%d.%H%M%S)}   # contract: times are UTC (HANDOVER §14)
BUILD_ARGS=${BUILD_ARGS:-}

echo "===== START ====="
echo "PROJECT=$PROJECT"
echo "MODE=$MODE"
echo "VERSION=$VERSION"
echo "DEV_CONTAINER=$DEV_CONTAINER"
echo "PWD=$(pwd)"
echo "DATE=$(date)"

echo "===== BUILD ====="

docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
cd '$PROJECT_DIR' &&
git pull
"

# Self-update: this script runs from the copy on the host, so git pull does not update it.
# The build target and the script version (git commit) should match, so
# if the repository HEAD after pull differs from the stamped version, update the script.
# If the script body changed, exit with RESTART REQUIRED and have it run again.
REPO_SHA="$(docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "cd '$PROJECT_DIR' && git rev-parse --short HEAD")"
echo "repo version: $REPO_SHA / script version: $BUILD_REMOTE_VERSION"

if [ "$BUILD_REMOTE_VERSION" != "$REPO_SHA" ]; then
    SELF_PATH="$SCRIPT_DIR/$(basename "$0")"
    NEW_SELF="$SCRIPT_DIR/.build-remote.sh.new"
    docker cp "$DEV_CONTAINER:$PROJECT_DIR/scripts/build-remote.sh" "$NEW_SELF"
    sed -i "s|^BUILD_REMOTE_VERSION=.*|BUILD_REMOTE_VERSION=\"$REPO_SHA\"|" "$NEW_SELF"
    chmod +x "$NEW_SELF"
    if diff <(grep -v '^BUILD_REMOTE_VERSION=' "$NEW_SELF") \
            <(grep -v '^BUILD_REMOTE_VERSION=' "$SELF_PATH") >/dev/null; then
        # The script body is identical (commit touched other files only). Update just the stamp and continue
        mv "$NEW_SELF" "$SELF_PATH"
        echo "script unchanged; version stamp updated to $REPO_SHA"
    else
        mv "$NEW_SELF" "$SELF_PATH"
        echo ""
        echo "===== RESTART REQUIRED ====="
        echo "Updated build-remote.sh from $BUILD_REMOTE_VERSION to $REPO_SHA."
        echo "Run it again: $SELF_PATH"
        exit 2
    fi
fi

docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
cd '$PROJECT_DIR' &&
./scripts/build.sh --app-version '$VERSION' $BUILD_ARGS
"

echo "===== PICK ====="

# Extract the deploy bundle (image.tar / .image-version / docker-compose.yml / scripts/deploy.sh /
# entrypoint.sh / README.md) directly into this directory.
# deploy.sh assumes "image.tar directly under the destination directory, itself under scripts/".
docker cp "$DEV_CONTAINER:$PROJECT_DIR/dist/deploy/." "$SCRIPT_DIR"
chmod +x "$SCRIPT_DIR/scripts/deploy.sh" "$SCRIPT_DIR/entrypoint.sh"

# Remove the extracted tar from the container (do not let them pile up)
docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
rm -f '$PROJECT_DIR/dist/deploy/image.tar'
"

echo "===== DEPLOY ====="

"$SCRIPT_DIR/scripts/deploy.sh" "$MODE"

echo "===== END ====="
