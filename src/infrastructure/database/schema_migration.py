"""Bring the DB schema to Alembic's head.

In production the entry point is ``scripts/run_db_migrations.py`` (the container entrypoint runs it before uvicorn).
The app itself (lifespan) never changes the schema; it only checks that it is at head (ADR-0006).

A DB from before Alembic (tables exist but no ``alembic_version``) replays the former
``create_all`` + hand-written column additions once to reach the same shape as baseline, and
is ``stamp``ed to baseline **only after confirming the shapes match**. A mismatch is never stamped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import StaticPool

BASELINE_REVISION = "0001"
VERSION_TABLE = "alembic_version"
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"

# Columns added by the hand-written ``ALTER TABLE ... ADD COLUMN`` have ``DEFAULT 'ja'``, because SQLite
# requires a default for NOT NULL (the create_all shape has none).
# The app always writes a value, so this one difference is treated as the same shape.
_TOLERATED_SERVER_DEFAULTS = frozenset({("users", "language")})


class LegacySchemaMismatchError(RuntimeError):
    """Could not bring a pre-Alembic DB to the baseline shape (not stamped)."""


class SchemaNotCurrentError(RuntimeError):
    """The DB is not at head (run scripts/run_db_migrations.py first)."""


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(str(_ALEMBIC_INI))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def migration_engine(database_url: str) -> Engine:
    """Connection for schema changes. Puts DDL in a single transaction even on SQLite.

    pysqlite does not emit BEGIN before DDL (it auto-commits). To **roll back everything** if
    the column additions, stamp or upgrade fail anywhere, we emit BEGIN ourselves.
    """
    if not database_url.startswith("sqlite"):
        return sa.create_engine(database_url)
    engine = sa.create_engine(database_url, connect_args={"check_same_thread": False})

    @sa.event.listens_for(engine, "connect")
    def _disable_pysqlite_transactions(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None

    @sa.event.listens_for(engine, "begin")
    def _begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


def upgrade_to_head(database_url: str) -> None:
    engine = migration_engine(database_url)
    try:
        with engine.begin() as connection:
            config = alembic_config(connection)
            tables = set(sa.inspect(connection).get_table_names())
            if tables and VERSION_TABLE not in tables:
                adopt_legacy_schema(connection)
                command.stamp(config, BASELINE_REVISION)
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def ensure_schema_is_current(engine: Engine) -> None:
    with engine.connect() as connection:
        current = current_revision(connection)
    head = head_revision()
    if current != head:
        raise SchemaNotCurrentError(
            f"the DB schema is at {current!r}, not head ({head!r}). "
            "Run scripts/run_db_migrations.py first"
        )


# ── Adopting a pre-Alembic DB ────────────────────────────────────────────────


def adopt_legacy_schema(connection: Connection) -> None:
    """Bring a pre-Alembic DB to the same shape as baseline. Raises if it does not match (no stamp).

    It does the same as what used to run on every startup:
    create missing tables (like ``create_all``) -> the 3 hand-written column additions -> create missing indexes.
    Table and index DDL is copied from baseline applied to an empty DB, so even the text matches baseline.
    """
    if connection.dialect.name != "sqlite":
        raise LegacySchemaMismatchError(
            f"a {connection.dialect.name} DB without alembic_version is not adopted (SQLite only)"
        )
    reference = _baseline_reference()
    try:
        reference_ddl = _schema_ddl(reference)
        expected = describe_schema(reference)
    finally:
        reference.close()
    existing = set(_schema_ddl(connection))

    for name, (kind, sql) in reference_ddl.items():
        if kind == "table" and name not in existing:
            connection.exec_driver_sql(sql)
    _apply_legacy_column_upgrades(connection)
    for name, (kind, sql) in reference_ddl.items():
        if kind == "index" and name not in existing:
            connection.exec_driver_sql(sql)

    actual = describe_schema(connection)
    if actual != expected:
        raise LegacySchemaMismatchError(
            "could not bring the existing DB to the baseline shape (not stamped)."
            f" diff: {_describe_difference(expected, actual)}"
        )


def _apply_legacy_column_upgrades(connection: Connection) -> None:
    # Column additions the pre-Alembic session.py applied on every startup (text kept verbatim).
    inspector = sa.inspect(connection)
    user_columns = {c["name"] for c in inspector.get_columns("users")}
    if "language" not in user_columns:
        connection.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN language VARCHAR(8) NOT NULL DEFAULT 'ja'"
        )
    auth_session_columns = {c["name"] for c in inspector.get_columns("auth_sessions")}
    if "idp_session_id" not in auth_session_columns:
        connection.exec_driver_sql("ALTER TABLE auth_sessions ADD COLUMN idp_session_id VARCHAR(255)")
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "remaining_hours" in task_columns:
        connection.exec_driver_sql("ALTER TABLE tasks DROP COLUMN remaining_hours")


def _baseline_reference() -> Connection:
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    connection = engine.connect()
    command.upgrade(alembic_config(connection), BASELINE_REVISION)
    connection.commit()
    return connection


def _schema_ddl(connection: Connection) -> dict[str, tuple[str, str]]:
    rows = connection.exec_driver_sql(
        "SELECT name, type, sql FROM sqlite_master "
        "WHERE type IN ('table', 'index') AND sql IS NOT NULL AND name <> ?",
        (VERSION_TABLE,),
    )
    return {name: (kind, sql) for name, kind, sql in rows}


def describe_schema(connection: Connection) -> dict[str, dict[str, Any]]:
    """Per-table shape (columns, primary key, unique constraints, foreign keys, indexes). A copy for comparison only."""
    inspector = sa.inspect(connection)
    schema: dict[str, dict[str, Any]] = {}
    for table in sorted(inspector.get_table_names()):
        if table == VERSION_TABLE:
            continue
        columns = {}
        for column in inspector.get_columns(table):
            default = column.get("default")
            if (table, column["name"]) in _TOLERATED_SERVER_DEFAULTS:
                default = None
            columns[column["name"]] = (str(column["type"]), bool(column["nullable"]), default)
        schema[table] = {
            "columns": columns,
            "primary_key": tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
            "unique": sorted(
                (u["name"] or "", tuple(u["column_names"]))
                for u in inspector.get_unique_constraints(table)
            ),
            "foreign_keys": sorted(
                (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
                for fk in inspector.get_foreign_keys(table)
            ),
            "indexes": sorted(
                (i["name"] or "", tuple(i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(table)
            ),
        }
    return schema


def _describe_difference(expected: dict[str, Any], actual: dict[str, Any]) -> str:
    parts = []
    for table in sorted(set(expected) | set(actual)):
        if expected.get(table) != actual.get(table):
            parts.append(f"{table}: expected {expected.get(table)} / actual {actual.get(table)}")
    return "; ".join(parts)
