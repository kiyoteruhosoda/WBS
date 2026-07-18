#!/usr/bin/env sh
# コンテナ entrypoint。ランタイム依存は uv が作る /app/.venv 側にのみ入っているため、
# 素の `python`（システム Python）ではなく必ず venv の Python で実行する。
set -eu
mode="${1:-app}"
python=/app/.venv/bin/python
case "$mode" in
  app|migrate) "$python" scripts/run_db_migrations.py ;;
  reset) rm -f /app/data/app.db app.db; "$python" scripts/run_db_migrations.py; "$python" scripts/seed_master_data.py ;;
  *) echo "unknown mode: $mode" >&2; exit 64 ;;
esac
[ "$mode" = "migrate" ] && exit 0
exec "$python" -m uvicorn main:app --host 0.0.0.0 --port 8000
