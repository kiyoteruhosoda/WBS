#!/usr/bin/env sh
set -eu
mode="${1:-app}"
case "$mode" in
  app|migrate) python scripts/run_db_migrations.py ;;
  reset) rm -f /app/data/app.db app.db; python scripts/run_db_migrations.py; python scripts/seed_master_data.py ;;
  *) echo "unknown mode: $mode" >&2; exit 64 ;;
esac
[ "$mode" = "migrate" ] && exit 0
exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
