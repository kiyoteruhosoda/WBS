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
./scripts/build.sh --target deploy # dist/deploy に image tar と host entrypoint を生成（明示指定）
```

高速化したい場合は `--skip-tests` や `--skip-frontend-install` を指定できます。frontend build は開発時の lockfile 不整合を自動補正できるよう、依存解決に `npm install` を使います。backend build は `uv` があれば `uv run`、なければ実行中の Python に必要な dev dependencies を `pip install -e . ruff pytest httpx` で補完してから `python -m ruff` / `python -m pytest` にフォールバックします。

## Deploy bundle

`./scripts/build.sh --app-version <tag>`（または明示的に `--target deploy`）は `dist/deploy/` に次を生成します。

- `wbs-images.tar`: `wbs-api:<tag>` と `wbs-web:<tag>` をまとめた Docker image tar
- `docker-compose.yml`: build 済み image を参照するホスト用 Compose ファイル
- `entrypoint.sh`: ホスト側で `docker load` と `docker compose up -d` を実行する起動スクリプト

生成後は `dist/deploy/` ディレクトリごとホストへコピーし、ホスト側で `./entrypoint.sh` を実行してください。
