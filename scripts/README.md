# scripts

- `entrypoint.sh app`: DB 初期化後に API を起動します。
- `entrypoint.sh migrate`: DB 初期化・マイグレーション相当のみ実行し、既存データを保持します。
- `entrypoint.sh reset`: SQLite DB を削除して初期ユーザーを再投入します（破壊的）。
- `build.sh`: API / Web / Docker イメージのビルドをまとめて実行する薄いラッパーです。
- `build.py`: `BuildStep` のポリモーフィズムで lint・test・frontend build・Docker build を合成するビルドオーケストレーターです。

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
- `docker-compose.yml`: build 済み image を参照するホスト用 Compose ファイル
- `scripts/deploy.sh`: 配置ディレクトリ名 `stg` / `prod` から環境を自動判定し、stg/prod を引数に含めず `app` / `migrate` / `reset` だけで実行するデプロイスクリプト
- `entrypoint.sh`: `scripts/deploy.sh` を呼ぶ薄い互換ラッパー

生成後は `dist/deploy/` の中身を `wbs/stg/` または `wbs/prod/` にコピーし、ホスト側で `./scripts/deploy.sh app`（または `migrate` / `reset`）を実行してください。環境は配置先ディレクトリ名から自動判定されるため、`./scripts/deploy.sh stg app` のような環境名引数は不要です。

デプロイ後の運用は手放しです:

- 全サービスに `restart: unless-stopped` を設定しているため、ホスト再起動・コンテナ異常終了後も Docker が自動で立ち上げ直します（再デプロイ不要）。
- `app` モードでは api コンテナの entrypoint が起動時に DB マイグレーションを自動実行します。
- 外部からの待受ポートは web (nginx) の 1 ポートのみで、既定は prod `8100` / stg `8101`（`.env` の `WEB_HOST_PORT` で上書き可能）。api はネットワーク内部専用で、外部からは `/api/` プロキシ経由で到達します。
