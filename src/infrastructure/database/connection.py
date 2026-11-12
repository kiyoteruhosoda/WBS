from __future__ import annotations

from src.infrastructure.database.schema_migration import upgrade_to_head
from src.infrastructure.database.session import (
    init_engine,
    resolve_database_url,
    seed_default_user,
)


def init_db(database_url: str | None = None) -> None:
    """Migrate the DB to head, set up the connection, and insert the default user (id=1). Idempotent.

    In production the container entrypoint (scripts/run_db_migrations.py) calls this before uvicorn.
    """
    url = resolve_database_url(database_url)
    upgrade_to_head(url)
    init_engine(url)
    seed_default_user()
