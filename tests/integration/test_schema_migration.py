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


def test_0006_leaves_existing_events_without_an_alarm_and_downgrades_cleanly(tmp_path):
    # task #183 / ADR-0021: 既存の予定は通知なし（alarm_enabled が NULL）
    url = _url(tmp_path, "alarms.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0005")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                "created_at, updated_at) VALUES "
                "(1, 'taro@example.com', '太郎', 'Asia/Tokyo', 'ja', 1, '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO calendar_events (id, user_id, kind, title, time_zone, start_utc, "
                "duration_minutes, color_key, span_start_day, span_end_day, version, "
                "created_at, updated_at) VALUES (1, 1, 'SINGLE', '定例', 'Asia/Tokyo', "
                "'2026-10-05 00:00:00', 60, 'DEFAULT', 1, 2, 1, '2026-01-01', '2026-01-01')"
            )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0006")
        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT alarm_enabled, alarm_15_min, alarm_5_min, alarm_1_min, alarm_at_start "
                "FROM calendar_events"
            ).one()
        assert row[0] is None
        assert [bool(v) for v in row[1:]] == [False, False, False, False]

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0005")
        columns = {c["name"] for c in sa.inspect(engine).get_columns("calendar_events")}
        assert {
            "alarm_enabled", "alarm_15_min", "alarm_5_min", "alarm_1_min", "alarm_at_start"
        }.isdisjoint(columns)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM calendar_events").scalar() == 1
    finally:
        engine.dispose()


def test_0007_leaves_existing_tasks_and_milestones_unclassified(tmp_path):
    # task #187 / ADR-0024: 移行はプロジェクトを作らない。既存のタスク・マイルストーンは未分類のまま
    url = _url(tmp_path, "projects.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0006")
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                "created_at, updated_at) VALUES "
                "(1, 'taro@example.com', '太郎', 'Asia/Tokyo', 'ja', 1, '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO milestones (id, user_id, name, created_at, updated_at) "
                "VALUES (1, 1, '節目', '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO tasks (id, user_id, title, priority, urgency, status, milestone_id, "
                "created_at, updated_at) VALUES (1, 1, 't', 3, 3, 'TODO', 1, '2026-01-01', '2026-01-01')"
            )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0007")
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT project_id, milestone_id FROM tasks").one() == (None, 1)
            assert connection.exec_driver_sql("SELECT project_id FROM milestones").one() == (None,)
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM projects").scalar() == 0

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0006")
        assert "projects" not in _tables(url)
        for table in ("tasks", "milestones"):
            columns = {c["name"] for c in sa.inspect(engine).get_columns(table)}
            assert "project_id" not in columns
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM tasks").scalar() == 1
    finally:
        engine.dispose()


def test_0008_makes_existing_events_plain_events_and_downgrades_cleanly(tmp_path):
    # task #190 / ADR-0025: 既存の予定は分類「予定」（EVENT）。済みの表は下げると消える
    url = _url(tmp_path, "event_types.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            config = alembic_config(connection)
            previous = ScriptDirectory.from_config(config).get_revision("0008").down_revision
            command.upgrade(config, previous)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                "created_at, updated_at) VALUES "
                "(1, 'taro@example.com', '太郎', 'Asia/Tokyo', 'ja', 1, '2026-01-01', '2026-01-01')"
            )
            connection.exec_driver_sql(
                "INSERT INTO calendar_events (id, user_id, kind, title, time_zone, start_utc, "
                "duration_minutes, color_key, span_start_day, span_end_day, version, "
                "created_at, updated_at) VALUES (1, 1, 'SINGLE', '定例', 'Asia/Tokyo', "
                "'2026-10-05 00:00:00', 60, 'DEFAULT', 1, 2, 1, '2026-01-01', '2026-01-01')"
            )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0008")
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT event_type FROM calendar_events"
            ).scalar() == "EVENT"
        assert "calendar_event_completions" in sa.inspect(engine).get_table_names()

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), previous)
        inspector = sa.inspect(engine)
        assert "calendar_event_completions" not in inspector.get_table_names()
        assert "event_type" not in {c["name"] for c in inspector.get_columns("calendar_events")}
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM calendar_events").scalar() == 1
    finally:
        engine.dispose()


def test_0009_puts_existing_events_into_a_default_calendar_per_user(tmp_path):
    # task #191 / ADR-0027: 利用者ごとに既定のカレンダー「予定」を作り、既存の予定はそこへ入れる
    url = _url(tmp_path, "calendars.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0008")
        with engine.begin() as connection:
            for user_id, email in ((1, "taro@example.com"), (2, "hanako@example.com"), (3, "none@example.com")):
                connection.exec_driver_sql(
                    "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                    f"created_at, updated_at) VALUES ({user_id}, '{email}', 'u', 'Asia/Tokyo', 'ja', 1, "
                    "'2026-01-01', '2026-01-01')"
                )
            for event_id, user_id in ((1, 1), (2, 2), (5, 1)):
                connection.exec_driver_sql(
                    "INSERT INTO calendar_events (id, user_id, kind, title, time_zone, start_utc, "
                    "duration_minutes, color_key, span_start_day, span_end_day, version, "
                    f"created_at, updated_at) VALUES ({event_id}, {user_id}, 'SINGLE', '定例', "
                    "'Asia/Tokyo', '2026-10-05 00:00:00', 60, 'DEFAULT', 1, 2, 1, "
                    "'2026-01-01', '2026-01-01')"
                )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0009")
        with engine.connect() as connection:
            calendars = connection.exec_driver_sql(
                "SELECT id, user_id, kind, name, color_key, is_default, is_visible FROM calendars "
                "ORDER BY user_id"
            ).all()
            assert [(c[1], c[2], c[3], c[4], bool(c[5]), bool(c[6])) for c in calendars] == [
                (1, "EVENTS", "予定", "DEFAULT", True, True),
                (2, "EVENTS", "予定", "DEFAULT", True, True),
                (3, "EVENTS", "予定", "DEFAULT", True, True),
            ]
            default_of = {c[1]: c[0] for c in calendars}
            events = connection.exec_driver_sql(
                "SELECT id, user_id, calendar_id FROM calendar_events ORDER BY id"
            ).all()
            assert [(e[0], e[2]) for e in events] == [
                (1, default_of[1]), (2, default_of[2]), (5, default_of[1]),
            ]
            # 作り直した表は消した予定の id を使い回さない（採番の最大を覚える）
            assert connection.exec_driver_sql(
                "SELECT seq FROM sqlite_sequence WHERE name = 'calendar_events'"
            ).scalar() == 5
        columns = {c["name"]: c for c in sa.inspect(engine).get_columns("calendar_events")}
        assert columns["calendar_id"]["nullable"] is False

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0008")
        inspector = sa.inspect(engine)
        assert {"calendars", "calendar_view_presets"}.isdisjoint(inspector.get_table_names())
        assert "calendar_id" not in {c["name"] for c in inspector.get_columns("calendar_events")}
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM calendar_events").scalar() == 3
            assert connection.exec_driver_sql(
                "SELECT seq FROM sqlite_sequence WHERE name = 'calendar_events'"
            ).scalar() == 5
    finally:
        engine.dispose()


def test_0010_makes_four_day_off_layers_and_copies_business_calendar_holidays(tmp_path):
    # task #191 / ADR-0029: 利用者ごとに 4 層。営業日の曜日はいちばん古い営業日カレンダーのもの、
    # 営業日カレンダーの祝日は「日本の祝日」の層へ（同じ日は 1 つ）
    url = _url(tmp_path, "day_off_layers.db")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0009")
        with engine.begin() as connection:
            for user_id, email in ((1, "taro@example.com"), (2, "hanako@example.com")):
                connection.exec_driver_sql(
                    "INSERT INTO users (id, email, display_name, timezone, language, is_active, "
                    f"created_at, updated_at) VALUES ({user_id}, '{email}', 'u', 'Asia/Tokyo', 'ja', 1, "
                    "'2026-01-01', '2026-01-01')"
                )
            for calendar_id, workdays in ((1, "MO,TU,WE,TH"), (2, "MO,TU,WE,TH,FR,SA")):
                connection.exec_driver_sql(
                    "INSERT INTO business_calendars (id, user_id, name, time_zone, workdays, "
                    "shift_on_holidays_only, is_enabled, created_at, updated_at) VALUES "
                    f"({calendar_id}, 1, '暦{calendar_id}', 'Asia/Tokyo', '{workdays}', 0, 1, "
                    "'2026-01-01', '2026-01-01')"
                )
            for calendar_id, day, name in (
                (1, "2026-10-12", "スポーツの日"), (2, "2026-10-12", "別名"), (2, "2026-11-03", "文化の日"),
            ):
                connection.exec_driver_sql(
                    "INSERT INTO business_calendar_holidays (calendar_id, holiday_date, name) "
                    f"VALUES ({calendar_id}, '{day}', '{name}')"
                )
        with engine.begin() as connection:
            command.upgrade(alembic_config(connection), "0010")
        with engine.connect() as connection:
            layers = connection.exec_driver_sql(
                "SELECT user_id, kind, name, workdays, day_off_reason, counts_as_day_off FROM calendars "
                "WHERE kind <> 'EVENTS' ORDER BY user_id, sort_order"
            ).all()
            assert [tuple(row[:5]) + (bool(row[5]),) for row in layers] == [
                (1, "WORKWEEK", "営業日", "MO,TU,WE,TH", None, False),
                (1, "DAYS_OFF", "会社の公休", None, "COMPANY", True),
                (1, "DAYS_OFF", "私の休み", None, "PERSONAL", True),
                (1, "DAYS_OFF", "日本の祝日", None, "NATIONAL_HOLIDAY", True),
                (2, "WORKWEEK", "営業日", "MO,TU,WE,TH,FR", None, False),
                (2, "DAYS_OFF", "会社の公休", None, "COMPANY", True),
                (2, "DAYS_OFF", "私の休み", None, "PERSONAL", True),
                (2, "DAYS_OFF", "日本の祝日", None, "NATIONAL_HOLIDAY", True),
            ]
            days = connection.exec_driver_sql(
                "SELECT c.user_id, d.day, d.name FROM calendar_days_off d "
                "JOIN calendars c ON c.id = d.calendar_id ORDER BY d.day"
            ).all()
            assert [tuple(d) for d in days] == [
                (1, "2026-10-12", "スポーツの日"), (1, "2026-11-03", "文化の日"),
            ]

        with engine.begin() as connection:
            command.downgrade(alembic_config(connection), "0009")
        inspector = sa.inspect(engine)
        assert "calendar_days_off" not in inspector.get_table_names()
        assert {"workdays", "day_off_reason", "counts_as_day_off"}.isdisjoint(
            {c["name"] for c in inspector.get_columns("calendars")}
        )
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM calendars WHERE kind <> 'EVENTS'"
            ).scalar() == 0
            assert connection.exec_driver_sql("SELECT COUNT(*) FROM calendars").scalar() == 2
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM business_calendar_holidays"
            ).scalar() == 3
    finally:
        engine.dispose()
