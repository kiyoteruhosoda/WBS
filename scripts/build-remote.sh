#!/bin/bash
# 開発コンテナの外（デプロイ先ホスト）から WBS をビルド → 取り出し → デプロイする。
#
# 流れ:
#   BUILD  : 開発コンテナ内で git pull + ./scripts/build.sh --app-version <VERSION> を実行し、
#            dist/deploy/ に deploy bundle（image.tar / docker-compose.yml /
#            scripts/deploy.sh など）を作る
#   PICK   : deploy bundle 一式を docker cp でこのディレクトリへ取り出す
#   DEPLOY : ./scripts/deploy.sh <MODE> を実行する（docker load・retag・compose up・
#            ヘルスチェックは deploy.sh 側が行う）
#
# この script は wbs/stg/ または wbs/prod/ に単体で置いて使う（リポジトリの checkout は
# 不要）。環境（stg / prod）は配置ディレクトリ名から deploy.sh が自動判定する。
# ホストに置いたコピーは、git pull 後にリポジトリの HEAD とバージョン刻印を照合し、
# 不一致なら自分を更新する（自己更新）。script 本体に変更があった場合は
# RESTART REQUIRED（exit 2）で終了するので、もう一度実行すること。
#
# 使い方:
#   ./build-remote.sh [run] [MODE]
#     MODE=app     : 通常デプロイ（既定）
#     MODE=migrate : コンテナ起動 + スキーマ同期
#     MODE=reset   : マウント済み SQLite データを削除して再構築（破壊的）
#   第 1 引数は Agent の args 登録用スロット（"run" など）で、値は使わない。
#
# 環境変数で上書き:
#   DEV_CONTAINER      ビルドを実行する開発コンテナ名（既定: ubuntu-dev）
#   DEV_CONTAINER_USER docker exec するユーザー（既定: sshuser）
#   PROJECT_DIR        コンテナ内のリポジトリパス（既定: /work/project/wbs）
#   VERSION            image バージョン（既定: 日時から自動生成）
#   BUILD_ARGS         build.sh へ渡す追加引数（例: "--skip-tests"）
set -euo pipefail

# ホストへ配布（自己更新）時にリポジトリの commit hash が刻印される。
# リポジトリ内のこのファイルでは常に unversioned のまま。
BUILD_REMOTE_VERSION="unversioned"

PROJECT=wbs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE=${2:-app}
case "$MODE" in
    app|migrate|reset) ;;
    *)
        echo "Usage: $0 [run] [app|migrate|reset]" >&2
        echo "  MODE '$MODE' は無効です。" >&2
        exit 1
        ;;
esac

DEV_CONTAINER=${DEV_CONTAINER:-ubuntu-dev}
DEV_CONTAINER_USER=${DEV_CONTAINER_USER:-sshuser}
PROJECT_DIR=${PROJECT_DIR:-/work/project/$PROJECT}
VERSION=${VERSION:-$(date +%Y.%m.%d.%H%M%S)}
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

# 自己更新: この script はホストに置いたコピーで動くため、git pull では更新されない。
# ビルド対象と script のバージョン（git commit）は一致しているべきなので、
# pull 後のリポジトリ HEAD と刻印バージョンが不一致なら script を更新する。
# script 本体に変更があった場合は RESTART REQUIRED として終了し、再実行してもらう。
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
        # script 本体は同一（他ファイルのみの commit）。刻印だけ更新して続行する
        mv "$NEW_SELF" "$SELF_PATH"
        echo "script unchanged; version stamp updated to $REPO_SHA"
    else
        mv "$NEW_SELF" "$SELF_PATH"
        echo ""
        echo "===== RESTART REQUIRED ====="
        echo "build-remote.sh を $BUILD_REMOTE_VERSION -> $REPO_SHA に更新しました。"
        echo "もう一度実行してください: $SELF_PATH"
        exit 2
    fi
fi

docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
cd '$PROJECT_DIR' &&
./scripts/build.sh --app-version '$VERSION' $BUILD_ARGS
"

echo "===== PICK ====="

# deploy bundle（image.tar / .image-version / docker-compose.yml / scripts/deploy.sh /
# entrypoint.sh / README.md）をこのディレクトリ直下へ展開する。
# deploy.sh は「配置ディレクトリ直下に image.tar、scripts/ 配下に自分」を前提とする。
docker cp "$DEV_CONTAINER:$PROJECT_DIR/dist/deploy/." "$SCRIPT_DIR"
chmod +x "$SCRIPT_DIR/scripts/deploy.sh" "$SCRIPT_DIR/entrypoint.sh"

# 取り出し済みの tar はコンテナ側から消しておく（溜め込まない）
docker exec -u "$DEV_CONTAINER_USER" "$DEV_CONTAINER" bash -lc "
rm -f '$PROJECT_DIR/dist/deploy/image.tar'
"

echo "===== DEPLOY ====="

"$SCRIPT_DIR/scripts/deploy.sh" "$MODE"

echo "===== END ====="
