from __future__ import annotations

from src.infrastructure.database.schema_migration import upgrade_to_head
from src.infrastructure.database.session import (
    init_engine,
    resolve_database_url,
    seed_default_user,
)


def init_db(database_url: str | None = None) -> None:
    """DB を head まで上げ、接続を用意し、既定の利用者（id=1）を入れる。冪等。

    本番ではコンテナの entrypoint（scripts/run_db_migrations.py）が uvicorn の前に呼ぶ。
    """
    url = resolve_database_url(database_url)
    upgrade_to_head(url)
    init_engine(url)
    seed_default_user()
