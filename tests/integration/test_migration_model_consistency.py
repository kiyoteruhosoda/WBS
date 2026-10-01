"""Alembic のリビジョンとモデル（models.py）が同じ形を作ることの確かめ。

⚠ モデルを変えたのにリビジョンを足し忘れると、ここが落ちる（足し方は migrations/README）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect, text

from src.infrastructure.database.models import Base
from src.infrastructure.database.schema_migration import describe_schema, upgrade_to_head


def _create_with_legacy_path(engine: sa.Engine) -> None:
    """Alembic 導入前の session.init_engine がしていたこと（比べるためだけに残す）。"""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "language" not in user_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'ja'"))
    auth_session_columns = {c["name"] for c in inspector.get_columns("auth_sessions")}
    if "idp_session_id" not in auth_session_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE auth_sessions ADD COLUMN idp_session_id VARCHAR(255)"))
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "remaining_hours" in task_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tasks DROP COLUMN remaining_hours"))


def test_upgrade_head_matches_create_all(tmp_path):
    migrated_url = f"sqlite:///{tmp_path / 'migrated.db'}"
    upgrade_to_head(migrated_url)
    legacy = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _create_with_legacy_path(legacy)
    migrated = sa.create_engine(migrated_url)

    with migrated.connect() as m, legacy.connect() as c:
        migrated_schema = describe_schema(m)
        legacy_schema = describe_schema(c)

    assert set(migrated_schema) == set(legacy_schema)
    for table in legacy_schema:
        assert migrated_schema[table] == legacy_schema[table], table


def test_upgrade_head_matches_models_by_autogenerate(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    upgrade_to_head(url)
    with sa.create_engine(url).connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
