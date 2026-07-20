# scripts

- `entrypoint.sh app`: DB 初期化後に API を起動します。
- `entrypoint.sh migrate`: DB 初期化・マイグレーション相当のみ実行し、既存データを保持します。
- `entrypoint.sh reset`: SQLite DB を削除して初期ユーザーを再投入します（破壊的）。
- `build.sh`: API / Web / Docker イメージのビルドをまとめて実行する薄いラッパーです。
- `build.py`: `BuildStep` のポリモーフィズムで lint・test・frontend build・Docker build を合成するビルドオーケストレーターです。
- `build-remote.sh`: デプロイ先ホストに単体で置き、開発コンテナ内ビルド→bundle 取り出し→デプロイをワンコマンドで行うスクリプトです（下記「Remote build & deploy」参照）。

現在は軽量 MVP として `init_db()` が冪等なスキーマ作成を担当します。将来 Alembic 導入時は `run_db_migrations.py` を `alembic upgrade head` に置き換えます。

## Build

```bash
./scripts/build.sh                 # deploy bundle を生成（デフォルト）
./scripts/build.sh --target api    # API lint/test のみ
./scripts/build.sh --target web    # Web install/build のみ
./scripts/build.sh --target docker # Docker image build
./scripts/build.sh --target deploy # dist/deploy に image.tar と scripts/deploy.sh を生成（明示指定）
```

高速化したい場合は `--skip-tests` や `--skip-frontend-install` を指定できます。frontend build は開発時の lockfile 不整合を自動補正できるよう、依存解決に `npm install` を使います。backend build は `uv` があれば `uv run`、なければ実行中の Python に必要な dev dependencies を `pip install -e . ruff pytest httpx` で補完してから `python -m ruff` / `python -m pytest` にフォールバックします。

## Deploy bundle

`./scripts/build.sh --app-version <tag>`（または明示的に `--target deploy`）は `dist/deploy/` に次を生成します。

- `image.tar`: `wbs-api:<tag>` と `wbs-web:<tag>` をまとめた Docker image tar
- `.image-version`: stg/prod 用タグへ付け替えるための build 元 tag
- `docker-compose.yml`: build 済み image を参照するホスト用 Compose ファイル（出所は `docker/deploy/docker-compose.yml`。api イメージにも焼き込まれ、`deploy.sh` がデプロイのたびにイメージ内のコピーで配置先を上書きするため、配置先での手編集は残らない。環境差は `.env` で表現する）
- `scripts/deploy.sh`: 配置ディレクトリ名 `stg` / `prod` から環境を自動判定し、stg/prod を引数に含めず `app` / `migrate` / `reset` だけで実行するデプロイスクリプト
- `entrypoint.sh`: `scripts/deploy.sh` を呼ぶ薄い互換ラッパー

生成後は `dist/deploy/` の中身を `wbs/stg/` または `wbs/prod/` にコピーし、ホスト側で `./scripts/deploy.sh app`（または `migrate` / `reset`）を実行してください。環境は配置先ディレクトリ名から自動判定されるため、`./scripts/deploy.sh stg app` のような環境名引数は不要です。

配置先に `.env` が無い場合、`deploy.sh` が初回実行時にコメント付きテンプレート（`HOST_DATA_ROOT` / `WEB_HOST_PORT` の実値＋上書き推奨キーのサンプル）を自動生成します。ローカル compose 用のサンプルはリポジトリ直下の `.env.example` を参照してください（デプロイ側とはキーが一部異なります: `WEB_PORT` ↔ `WEB_HOST_PORT`）。

デプロイ後の運用は手放しです:

- 全サービスに `restart: unless-stopped` を設定しているため、ホスト再起動・コンテナ異常終了後も Docker が自動で立ち上げ直します（再デプロイ不要）。
- `app` モードでは api コンテナの entrypoint が起動時に DB マイグレーションを自動実行します。
- 外部からの待受ポートは web (nginx) の 1 ポートのみで、既定は prod `8100` / stg `8101`（`.env` の `WEB_HOST_PORT` で上書き可能）。api はネットワーク内部専用で、外部からは `/api/` プロキシ経由で到達します。
- デプロイ末尾にはデプロイされたバージョン（`APP_VERSION` / `GIT_SHA` / `BUILD_TIME`）を表示します。ヘルスチェック失敗時は api の healthcheck 履歴（`docker inspect .State.Health`）も診断出力に含まれます。

## Remote build & deploy（build-remote.sh）

`scripts/build-remote.sh` は、デプロイ先ホスト（Synology 等）の `wbs/stg/` または `wbs/prod/` に**単体で**コピーして使います（ホスト側にリポジトリの checkout は不要）。実行すると次を一括で行います。

1. **BUILD**: 開発コンテナ（既定 `ubuntu-dev`）内で `git pull` → `./scripts/build.sh --app-version <VERSION>` を実行し `dist/deploy/` に deploy bundle を生成
2. **PICK**: bundle 一式（`image.tar` / `.image-version` / `docker-compose.yml` / `scripts/deploy.sh` / `entrypoint.sh`）を `docker cp` で**配置ディレクトリ直下**へ展開（`deploy.sh` は `<配置dir>/scripts/deploy.sh` に置かれる）
3. **DEPLOY**: `./scripts/deploy.sh <MODE>` を実行（load・retag・compose up・ヘルスチェックは `deploy.sh` が担当）

```bash
./build-remote.sh run app      # 通常デプロイ（MODE 省略時の既定）
./build-remote.sh run migrate  # コンテナ起動 + スキーマ同期
./build-remote.sh run reset    # データ削除して再構築（破壊的）
```

第 1 引数は DeployBridge Agent の args 登録用スロットで値は使いません。環境（stg / prod）は配置ディレクトリ名から `deploy.sh` が自動判定します。

ホストに置いたコピーは実行のたびに `git pull` 後のリポジトリ HEAD と自身のバージョン刻印を照合し、スクリプト本体に差分があれば自己更新して `RESTART REQUIRED`（exit 2）で終了します。その場合はもう一度実行してください。

環境変数で上書き可能: `DEV_CONTAINER` / `DEV_CONTAINER_USER` / `PROJECT_DIR` / `VERSION` / `BUILD_ARGS`（例: `BUILD_ARGS=--skip-tests`）。

### Docker リソースの命名

compose プロジェクト名は prod `wbs` / stg `wbs-stg`（`deploy.sh` の `-p` で固定）、ローカル開発はリポジトリ直下 compose の `name: wbs`。コンテナは `wbs-api-1` / `wbs-web-1` のように、ネットワーク・ボリュームは `wbs_...` のように、常に wbs プレフィックスで作成されます。イメージタグは build 時 `wbs-api:<tag>` / `wbs-web:<tag>`、デプロイ先では環境別に `wbs-api:stg|prod` / `wbs-web:stg|prod` へ付け替えます。
