# scripts

- `entrypoint.sh app`: DB 初期化後に API を起動します。
- `entrypoint.sh migrate`: DB 初期化・マイグレーション相当のみ実行し、既存データを保持します。
- `entrypoint.sh reset`: SQLite DB を削除して初期ユーザーを再投入します（破壊的）。
- `build.sh`: API / Web / Docker イメージのビルドをまとめて実行する薄いラッパーです。
- `build.py`: `BuildStep` のポリモーフィズムで lint・test・frontend build・Docker build を合成するビルドオーケストレーターです。

現在は軽量 MVP として `init_db()` が冪等なスキーマ作成を担当します。将来 Alembic 導入時は `run_db_migrations.py` を `alembic upgrade head` に置き換えます。

## Build

```bash
./scripts/build.sh                 # API lint/test + Web install/build
./scripts/build.sh --target api    # API lint/test のみ
./scripts/build.sh --target web    # Web install/build のみ
./scripts/build.sh --target docker # docker compose build
```

高速化したい場合は `--skip-tests` や `--skip-frontend-install` を指定できます。
