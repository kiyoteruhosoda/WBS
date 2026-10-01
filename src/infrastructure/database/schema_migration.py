"""DB の形を Alembic の head へ揃える。

本番の入口は ``scripts/run_db_migrations.py``（コンテナの entrypoint が uvicorn の前に流す）。
アプリ本体（lifespan）は形を変えず、head に揃っているかを確かめるだけ（ADR-0006）。

Alembic 導入前の DB（表はあるが ``alembic_version`` が無い）は、かつての
``create_all`` + 手書きの列補完を 1 回だけなぞって baseline と同じ形にし、
**同じ形になったと確かめてから** baseline へ ``stamp`` する。食い違ったままは stamp しない。
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

# 手書きの列補完が ``ALTER TABLE ... ADD COLUMN`` で足した列は、SQLite の決まりで
# NOT NULL に既定値が要るため ``DEFAULT 'ja'`` を持つ（create_all の形は持たない）。
# アプリは常に値を入れて書くので、この差だけは同じ形とみなす。
_TOLERATED_SERVER_DEFAULTS = frozenset({("users", "language")})


class LegacySchemaMismatchError(RuntimeError):
    """Alembic 導入前の DB を baseline の形へ揃えきれなかった（stamp しない）。"""


class SchemaNotCurrentError(RuntimeError):
    """DB が head まで上がっていない（先に scripts/run_db_migrations.py を流す）。"""


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
    """形を変えるための接続。SQLite でも DDL を 1 つの transaction に入れる。

    pysqlite は DDL の前に BEGIN を出さない（自動で確定してしまう）。補完・stamp・
    upgrade のどこかで落ちたら**全部を巻き戻す**ため、BEGIN を自分で出す。
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
            f"DB のスキーマが {current!r} で head（{head!r}）ではない。"
            "先に scripts/run_db_migrations.py を流すこと"
        )


# ── Alembic 導入前の DB の引き取り ──────────────────────────────────────────


def adopt_legacy_schema(connection: Connection) -> None:
    """Alembic 導入前の DB を baseline と同じ形にする。揃わなければ例外（stamp させない）。

    やることは、かつて起動のたびに走っていた処理と同じ:
    無い表を作る（``create_all`` 相当）→ 手書きの列補完 3 つ → 無い索引を作る。
    表と索引の DDL は baseline を空の DB へ当てた結果から写すので、文面まで baseline と同じになる。
    """
    if connection.dialect.name != "sqlite":
        raise LegacySchemaMismatchError(
            f"{connection.dialect.name} の、alembic_version の無い DB は引き取らない（SQLite のみ）"
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
            "既存の DB を baseline の形へ揃えきれなかった（stamp しない）。"
            f" 差: {_describe_difference(expected, actual)}"
        )


def _apply_legacy_column_upgrades(connection: Connection) -> None:
    # Alembic 導入前の session.py が起動のたびに当てていた列補完（文面もそのまま）。
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
    """表ごとの形（列・主キー・一意制約・外部キー・索引）。比べるためだけの写し。"""
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
            parts.append(f"{table}: 期待 {expected.get(table)} / 実際 {actual.get(table)}")
    return "; ".join(parts)
