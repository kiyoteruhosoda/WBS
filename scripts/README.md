# scripts

- `entrypoint.sh app`: DB 初期化後に API を起動します。
- `entrypoint.sh migrate`: DB 初期化・マイグレーション相当のみ実行し、既存データを保持します。
- `entrypoint.sh reset`: SQLite DB を削除して初期ユーザーを再投入します（破壊的）。

現在は軽量 MVP として `init_db()` が冪等なスキーマ作成を担当します。将来 Alembic 導入時は `run_db_migrations.py` を `alembic upgrade head` に置き換えます。
