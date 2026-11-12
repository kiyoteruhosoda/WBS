#!/usr/bin/env bash
# Writes src/infrastructure/version.json. The sole source for /info (and the settings page) to answer
# "which commit's image is running" (ADR-0011).
# The shape matches fastapitemplate's scripts/generate_version.sh (ADR-0044).
#
# Called from 3 places:
#   1. The "stamp the version" step of deck's build (the production path): when deploy-repo's
#      resources/build-matrix.json has `pre_build: true`, this runs at the root of the cloned
#      repository and its output goes into the Docker build context
#   2. The Dockerfile RUN: does **nothing** if 1 ran. Otherwise stamps dev
#   3. Local checks (scripts/build.py docker / deploy / direct run)
#
# Precedence: **git > existing version.json > dev**
#
# ⚠ Always regenerate where git is available. With a reused build directory (and
#   version.json being in .gitignore, so `git pull` does not remove it), "respecting the existing one"
#   would make every build after the first **keep claiming the first version**.
# ⚠ Conversely, inside the image (.git is excluded by .dockerignore) never overwrite the existing one.
#   Overwriting would let the Dockerfile RUN clobber the real version made by 1 with dev.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="${VERSION_FILE:-$PROJECT_ROOT/src/infrastructure/version.json}"

# --- 1. Generate from git (always regenerate where available) ----------------
# ⚠ `-c safe.directory=*` is required. The builder may run under a different UID from the
#   clone's owner, and without it git silently fails with "dubious ownership".
if command -v git >/dev/null 2>&1 && [ -e "$PROJECT_ROOT/.git" ]; then
    GIT=(git -c "safe.directory=*" -C "$PROJECT_ROOT")

    COMMIT_HASH=$("${GIT[@]}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    COMMIT_HASH_FULL=$("${GIT[@]}" rev-parse HEAD 2>/dev/null || echo "unknown")
    BRANCH=$("${GIT[@]}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    COMMIT_DATE=$("${GIT[@]}" log -1 --format=%cI 2>/dev/null || echo "unknown")

    # On a detached HEAD (deck/CI checkouts) BRANCH becomes "HEAD".
    # If the caller knows the branch name, it fills it in via BRANCH_OVERRIDE (deck passes it).
    if [ -n "${BRANCH_OVERRIDE:-}" ] && { [ "$BRANCH" = "HEAD" ] || [ "$BRANCH" = "unknown" ]; }; then
        BRANCH="$BRANCH_OVERRIDE"
    fi

    # ⚠ No `v` prefix. It is a short commit hash, not a meaningful version number,
    #   and a `v` would read as "such a release exists".
    if [ "$BRANCH" = "main" ]; then
        VERSION="$COMMIT_HASH"
    else
        VERSION="$COMMIT_HASH-$BRANCH"
    fi
    SOURCE="git"
elif [ -s "$VERSION_FILE" ] && grep -q '"commit_hash"' "$VERSION_FILE"; then
    # --- 2. No git = inside the image. The content placed before the build wins ----
    echo "[version] Using the existing version.json: $VERSION_FILE"
    cat "$VERSION_FILE"
    exit 0
else
    # --- 3. Neither (e.g. a bare `docker build`) ---------------------------------
    COMMIT_HASH="dev"
    COMMIT_HASH_FULL="dev"
    BRANCH="unknown"
    COMMIT_DATE="unknown"
    VERSION="dev"
    SOURCE="default"
fi

BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # contract: times are UTC with a trailing Z (HANDOVER §14)

mkdir -p "$(dirname "$VERSION_FILE")"
cat > "$VERSION_FILE" << JSON
{
  "version": "$VERSION",
  "commit_hash": "$COMMIT_HASH",
  "commit_hash_full": "$COMMIT_HASH_FULL",
  "branch": "$BRANCH",
  "commit_date": "$COMMIT_DATE",
  "build_date": "$BUILD_DATE"
}
JSON

echo "[version] Generated from $SOURCE: $VERSION ($COMMIT_HASH, $BRANCH) -> $VERSION_FILE"
