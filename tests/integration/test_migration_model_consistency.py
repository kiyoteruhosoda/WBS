"""Check that the Alembic revisions and the models (models.py) build the same schema.

⚠ If you change a model but forget to add a revision, this fails (how to add one: migrations/README).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect, text

from src.infrastructure.database.models import Base
from src.infrastructure.database.schema_migration import describe_schema, upgrade_to_head


def _create_with_legacy_path(engine: sa.Engine) -> None:
    """What session.init_engine did before Alembic was introduced (kept only for comparison)."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "language" not in user_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'ja'"))
    # The hand-written column backfill used to drop tasks.remaining_hours, but 0004 restored it as a column (ADR-0010).
    # create_all builds from the current models, so we don't drop it here.


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
