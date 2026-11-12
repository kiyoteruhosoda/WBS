from __future__ import annotations

import sys
from pathlib import Path

# Add the repository root to the import path so the `src` package resolves even when
# the script is run directly (`python scripts/run_db_migrations.py`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.database.connection import init_db  # noqa: E402

# The connection target is the DATABASE_URL environment variable (sqlite:///./app.db when unset).
# init_db() is idempotent: it runs Alembic upgrade head (DBs predating Alembic are first stamped
# at baseline) and seeds the initial user. On failure nothing is committed and it exits non-zero.
init_db()
