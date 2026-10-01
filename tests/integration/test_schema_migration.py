"""Alembic の上げ下げと、Alembic 導入前の DB の引き取り。"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.script import ScriptDirectory

from src.infrastructure.database.schema_migration import (
    BASELINE_REVISION,
    LegacySchemaMismatchError,
    SchemaNotCurrentError,
    alembic_config,
    current_revision,
    describe_schema,
    ensure_schema_is_current,
    head_revision,
    upgrade_to_head,
)

# Alembic 導入前・手書きの列補完が 1 つも当たっていない頃の形（凍結。models.py から作らない）。
# users.language / auth_sessions.idp_session_id（と索引）が無く、tasks.remaining_hours が残り、
# auth_backchannel_logout_deliveries がまだ無い。
LEGACY_DDL = [
    """CREATE TABLE users (
        id INTEGER NOT NULL, email VARCHAR(255) NOT NULL, display_name VARCHAR(100) NOT NULL,
        timezone VARCHAR(64) NOT NULL, is_active BOOLEAN NOT NULL,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), UNIQUE (email))""",
    """CREATE TABLE categories (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, name VARCHAR(100) NOT NULL,
        color VARCHAR(7), sort_order INTEGER NOT NULL, deleted_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), UNIQUE (user_id, name), FOREIGN KEY(user_id) REFERENCES users (id))""",
    """CREATE TABLE milestones (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, name VARCHAR(200) NOT NULL,
        due_date DATE, description TEXT, deleted_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), FOREIGN KEY(user_id) REFERENCES users (id))""",
    """CREATE TABLE tasks (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, title VARCHAR(500) NOT NULL,
        category_id INTEGER, priority SMALLINT NOT NULL, urgency SMALLINT NOT NULL,
        status VARCHAR(20) NOT NULL, start_date DATE, due_date DATE,
        estimated_hours NUMERIC(6, 2), remaining_hours NUMERIC(6, 2), memo TEXT,
        parent_task_id INTEGER, milestone_id INTEGER, completed_at DATETIME, deleted_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), FOREIGN KEY(user_id) REFERENCES users (id),
        FOREIGN KEY(category_id) REFERENCES categories (id),
        FOREIGN KEY(parent_task_id) REFERENCES tasks (id),
        FOREIGN KEY(milestone_id) REFERENCES milestones (id))""",
    """CREATE TABLE work_logs (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, task_id INTEGER NOT NULL,
        work_date DATE NOT NULL, hours NUMERIC(5, 2) NOT NULL, memo TEXT, deleted_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), FOREIGN KEY(user_id) REFERENCES users (id),
        FOREIGN KEY(task_id) REFERENCES tasks (id))""",
    """CREATE TABLE task_dependencies (
        predecessor_task_id INTEGER NOT NULL, successor_task_id INTEGER NOT NULL,
        dependency_type VARCHAR(2) NOT NULL, lag_days INTEGER NOT NULL, created_at DATETIME NOT NULL,
        PRIMARY KEY (predecessor_task_id, successor_task_id),
        FOREIGN KEY(predecessor_task_id) REFERENCES tasks (id),
        FOREIGN KEY(successor_task_id) REFERENCES tasks (id))""",
    """CREATE TABLE inbox_items (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, title VARCHAR(500) NOT NULL, memo TEXT,
        converted_task_id INTEGER, converted_at DATETIME, deleted_at DATETIME,
        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
        PRIMARY KEY (id), FOREIGN KEY(user_id) REFERENCES users (id),
        FOREIGN KEY(converted_task_id) REFERENCES tasks (id))""",
    """CREATE TABLE federated_identities (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, issuer VARCHAR(255) NOT NULL,
        subject VARCHAR(255) NOT NULL, created_at DATETIME NOT NULL,
        PRIMARY KEY (id), CONSTRAINT uq_federated_identity UNIQUE (issuer, subject),
        FOREIGN KEY(user_id) REFERENCES users (id))""",
    "CREATE INDEX ix_federated_identities_user_id ON federated_identities (user_id)",
    """CREATE TABLE auth_sessions (
        id INTEGER NOT NULL, user_id INTEGER NOT NULL, token_hash VARCHAR(64) NOT NULL,
        issued_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, last_seen_at DATETIME NOT NULL,
        PRIMARY KEY (id), FOREIGN KEY(user_id) REFERENCES users (id), UNIQUE (token_hash))""",
    "CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id)",
    "CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at)",
    """CREATE TABLE auth_login_transactions (
        id INTEGER NOT NULL, state VARCHAR(128) NOT NULL, nonce VARCHAR(128) NOT NULL,
        code_verifier VARCHAR(128) NOT NULL, redirect_path VARCHAR(512) NOT NULL,
        created_at DATETIME NOT NULL, expires_at DATETIME NOT NULL,
        PRIMARY KEY (id), UNIQUE (state))""",
    "CREATE INDEX ix_auth_login_transactions_expires_at ON auth_login_transactions (expires_at)",
]


def _url(tmp_path, name: str) -> str:
    return f"sqlite:///{tmp_path / name}"


def _tables(url: str) -> set[str]:
    engine = sa.create_engine(url)
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _schema(url: str) -> dict:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            return describe_schema(connection)
    finally:
        engine.dispose()


def _revision(url: str) -> str | None:
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            return current_revision(connection)
    finally:
        engine.dispose()


def _build_legacy_db(url: str, extra_ddl: list[str] | None = None) -> None:
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        for ddl in LEGACY_DDL + (extra_ddl or []):
            connection.exec_driver_sql(ddl)
        connection.exec_driver_sql(
            "INSERT INTO users (id, email, display_name, timezone, is_active, created_at, updated_at) "
            "VALUES (1, 'taro@example.com', '太郎', 'Asia/Tokyo', 1, '2026-01-01', '2026-01-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO tasks (id, user_id, title, priority, urgency, status, remaining_hours, "
            "created_at, updated_at) VALUES (7, 1, '残す', 3, 3, 'TODO', 1.5, '2026-01-01', '2026-01-01')"
        )
    engine.dispose()


def test_there_is_a_single_head():
    script = ScriptDirectory.from_config(alembic_config())
    assert len(script.get_heads()) == 1


def test_upgrade_downgrade_upgrade_on_an_empty_db(tmp_path):
    url = _url(tmp_path, "cycle.db")
    upgrade_to_head(url)
    first = _schema(url)
    assert "users" in first
    assert _revision(url) == head_revision()

    engine = sa.create_engine(url)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "base")
    engine.dispose()
    assert _tables(url) <= {"alembic_version"}
    assert _revision(url) is None

    upgrade_to_head(url)
    assert _schema(url) == first
    assert _revision(url) == head_revision()


def test_upgrade_to_head_is_idempotent(tmp_path):
    url = _url(tmp_path, "twice.db")
    upgrade_to_head(url)
    upgrade_to_head(url)
    assert _revision(url) == head_revision()


def test_legacy_db_is_brought_to_baseline_then_stamped(tmp_path):
    legacy_url = _url(tmp_path, "legacy.db")
    _build_legacy_db(legacy_url)
    fresh_url = _url(tmp_path, "fresh.db")
    upgrade_to_head(fresh_url)

    upgrade_to_head(legacy_url)

    assert _revision(legacy_url) == head_revision()
    assert _schema(legacy_url) == _schema(fresh_url)
    engine = sa.create_engine(legacy_url)
    with engine.connect() as connection:
        user = connection.exec_driver_sql("SELECT email, language FROM users WHERE id = 1").one()
        task = connection.exec_driver_sql("SELECT title FROM tasks WHERE id = 7").one()
        indexes = {i["name"] for i in sa.inspect(connection).get_indexes("auth_sessions")}
    engine.dispose()
    assert tuple(user) == ("taro@example.com", "ja")
    assert task.title == "残す"
    # 手書きの補完は列だけ足して索引を作っていなかった。baseline の形に揃える。
    assert "ix_auth_sessions_idp_session_id" in indexes


def test_legacy_db_that_cannot_be_matched_is_left_untouched(tmp_path):
    url = _url(tmp_path, "odd.db")
    # 補完の手が届かない差（baseline に無い列）を持つ古い DB
    _build_legacy_db(url, ["ALTER TABLE categories ADD COLUMN legacy_note TEXT"])
    before = _schema(url)

    with pytest.raises(LegacySchemaMismatchError):
        upgrade_to_head(url)

    # 1 つの transaction で巻き戻るので、補完も stamp も残らない
    assert _schema(url) == before
    assert "alembic_version" not in _tables(url)
    assert "remaining_hours" in before["tasks"]["columns"]


def test_app_engine_refuses_a_db_that_is_not_at_head(tmp_path):
    url = _url(tmp_path, "behind.db")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), BASELINE_REVISION)
    if head_revision() == BASELINE_REVISION:
        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "base")
    try:
        with pytest.raises(SchemaNotCurrentError):
            ensure_schema_is_current(engine)
    finally:
        engine.dispose()


def test_0004_fills_remaining_from_estimate_minus_actual(tmp_path):
    # task #165 / ADR-0010: 既存の行の残は、それまで画面に出ていた max(見積 − 実績, 0)。DONE は 0
    url = _url(tmp_path, "remaining.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0003")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                "created_at, updated_at) VALUES "
                "(1, 'taro@example.com', '太郎', 'Asia/Tokyo', 'ja', 1, '2026-01-01', '2026-01-01')"
            )
            for task_id, status, estimate in [
                (1, "TODO", "10"),  # 実績 4（削除した 3 は数えない）→ 6
                (2, "DOING", "5"),  # 実績 8 → 負にしない 0
                (3, "DONE", "10"),  # 実績 2 でも DONE は 0
                (4, "TODO", None),  # 見積が空 → 空のまま
                (5, "TODO", "7.5"),  # 実績なし → 7.5
            ]:
                connection.exec_driver_sql(
                    "INSERT INTO tasks (id, user_id, title, priority, urgency, status, "
                    "estimated_hours, created_at, updated_at) "
                    "VALUES (?, 1, 't', 3, 3, ?, ?, '2026-01-01', '2026-01-01')",
                    (task_id, status, estimate),
                )
            for log_id, task_id, hours, deleted_at in [
                (1, 1, "1.5", None),
                (2, 1, "2.5", None),
                (3, 1, "3", "2026-01-02"),
                (4, 2, "8", None),
                (5, 3, "2", None),
            ]:
                connection.exec_driver_sql(
                    "INSERT INTO work_logs (id, user_id, task_id, work_date, hours, deleted_at, "
                    "created_at, updated_at) "
                    "VALUES (?, 1, ?, '2026-01-01', ?, ?, '2026-01-01', '2026-01-01')",
                    (log_id, task_id, hours, deleted_at),
                )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0004")
        with engine.connect() as connection:
            rows = dict(
                connection.exec_driver_sql("SELECT id, remaining_hours FROM tasks").fetchall()
            )
        assert {k: (None if v is None else float(v)) for k, v in rows.items()} == {
            1: 6.0,
            2: 0.0,
            3: 0.0,
            4: None,
            5: 7.5,
        }

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0003")
        columns = {c["name"] for c in sa.inspect(engine).get_columns("tasks")}
        assert "remaining_hours" not in columns
    finally:
        engine.dispose()


def test_0005_marks_existing_work_logs_as_manual_and_downgrades_cleanly(tmp_path):
    # task #161 / ADR-0012: 締めより前の実績は手で書いたもの（開け直しで消えない）
    url = _url(tmp_path, "closing.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0004")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                "created_at, updated_at) VALUES "
                "(1, 'taro@example.com', '太郎', 'Asia/Tokyo', 'ja', 1, '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO tasks (id, user_id, title, priority, urgency, status, "
                "created_at, updated_at) VALUES (1, 1, 't', 3, 3, 'TODO', '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO work_logs (id, user_id, task_id, work_date, hours, "
                "created_at, updated_at) "
                "VALUES (1, 1, 1, '2026-01-01', 1.5, '2026-01-01', '2026-01-01')"
            )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0005")
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT source, closing_period_id, duration_seconds, hours FROM work_logs"
            ).one()
        assert (row[0], row[1], row[2], float(row[3])) == ("manual", None, None, 1.5)
        assert "closing_periods" in _tables(url)

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0004")
        columns = {c["name"] for c in sa.inspect(engine).get_columns("work_logs")}
        assert {"source", "closing_period_id", "duration_seconds"}.isdisjoint(columns)
        assert "closing_periods" not in _tables(url)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM work_logs").scalar() == 1
    finally:
        engine.dispose()
