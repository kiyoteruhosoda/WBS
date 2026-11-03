"""Tracker・Scheduler へ移した表を消す（task #543 / ADR-0070。Tracker の ADR-0053・Scheduler の ADR-0054 の段 4）

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-03

- 打刻まわり（Tracker へ 2026-10-19 に移した）: time_entries・time_entry_carvings・auto_time_entry_receipts・
  work_breaks・pc_activity_days・pc_activity_spans・tracking_rules・tracking_rule_books・closing_periods
- 予定まわり（Scheduler へ 2026-10-19 に移した）: calendars・calendar_days_off・calendar_imports・
  calendar_imported_occurrences・calendar_view_presets・calendar_events・calendar_event_exceptions・
  calendar_event_moves・calendar_event_completions
- 端末への通知（Web Push。4 種類とも Tracker・Scheduler が送る）: push_subscriptions・push_preferences・push_dispatches
- work_logs.closing_period_id（WBS の締めの期間を指す列）。行は残す（``source=closing`` のまま）

⚠ 中身は捨てる。写しは切り替えのときに Tracker・Scheduler へ取ってあり、WBS の DB は毎日退避している
（持ち主が承知のうえ・2026-11-03）。戻すと空の表ができる（中身は戻らない）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    # 先に子（参照する側）を消す。MariaDB は参照されている表を消せない
    with op.batch_alter_table("work_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_logs_closing_period_id"))
        batch_op.drop_constraint(batch_op.f("fk_work_logs_closing_period_id"), type_="foreignkey")
        batch_op.drop_column("closing_period_id")

    with op.batch_alter_table('push_dispatches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_dispatches_sent_at'))

    op.drop_table('push_dispatches')
    op.drop_table('push_preferences')
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_subscriptions_user_id'))

    op.drop_table('push_subscriptions')
    op.drop_table('calendar_event_completions')
    op.drop_table('calendar_event_moves')
    op.drop_table('calendar_event_exceptions')
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_events_calendar_id'))
        batch_op.drop_index(batch_op.f('ix_calendar_events_task_id'))
        batch_op.drop_index(batch_op.f('ix_calendar_events_user_span'))

    op.drop_table('calendar_events')
    with op.batch_alter_table('calendar_view_presets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_view_presets_user_id'))

    op.drop_table('calendar_view_presets')
    with op.batch_alter_table('calendar_imported_occurrences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendar_imported_occurrences_calendar_id'))

    op.drop_table('calendar_imported_occurrences')
    op.drop_table('calendar_imports')
    op.drop_table('calendar_days_off')
    with op.batch_alter_table('calendars', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calendars_user_id'))

    op.drop_table('calendars')
    op.drop_table('tracking_rule_books')
    with op.batch_alter_table('tracking_rules', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tracking_rules_user_id_position'))

    op.drop_table('tracking_rules')
    with op.batch_alter_table('pc_activity_spans', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pc_activity_spans_day_id'))
        batch_op.drop_index(batch_op.f('ix_pc_activity_spans_user_id_started_at'))

    op.drop_table('pc_activity_spans')
    op.drop_table('pc_activity_days')
    with op.batch_alter_table('work_breaks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_work_breaks_user_id_started_at'))

    op.drop_table('work_breaks')
    op.drop_table('auto_time_entry_receipts')
    with op.batch_alter_table('time_entry_carvings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_time_entry_carvings_user_id_window'))

    op.drop_table('time_entry_carvings')
    with op.batch_alter_table('time_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_time_entries_user_id_client_ref'))
        batch_op.drop_index(batch_op.f('ix_time_entries_user_id_started_at'))
        batch_op.drop_index(batch_op.f('uq_time_entries_running_per_user'), sqlite_where=sa.text('ended_at IS NULL'))

    op.drop_table('time_entries')
    op.drop_table('closing_periods')


def downgrade() -> None:
    # 親（参照される側）から作る
    op.create_table('closing_periods',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('first_day', sa.DATE(), nullable=False),
    sa.Column('last_day', sa.DATE(), nullable=False),
    sa.Column('time_zone', sa.VARCHAR(length=64), nullable=False),
    sa.Column('starts_at', sa.DATETIME(), nullable=False),
    sa.Column('ends_at', sa.DATETIME(), nullable=False),
    sa.Column('closed_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'first_day', name=op.f('uq_closing_periods_user_first_day')),
    sqlite_autoincrement=True,
    )
    op.create_table('time_entries',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('task_id', _ID, nullable=True),
    sa.Column('started_at', sa.DATETIME(), nullable=False),
    sa.Column('ended_at', sa.DATETIME(), nullable=True),
    sa.Column('memo', sa.TEXT(), nullable=True),
    sa.Column('source', sa.VARCHAR(length=16), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.Column('client_ref', sa.VARCHAR(length=64), nullable=True),
    sa.Column('auto_mode', sa.VARCHAR(length=16), nullable=True),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('time_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('uq_time_entries_running_per_user'), ['user_id'], unique=1, sqlite_where=sa.text('ended_at IS NULL'))
        batch_op.create_index(batch_op.f('ix_time_entries_user_id_started_at'), ['user_id', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_time_entries_user_id_client_ref'), ['user_id', 'client_ref'], unique=False)

    op.create_table('time_entry_carvings',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('client_ref', sa.VARCHAR(length=64), nullable=False),
    sa.Column('time_entry_id', _ID, nullable=False),
    sa.Column('action', sa.VARCHAR(length=16), nullable=False),
    sa.Column('task_id', _ID, nullable=True),
    sa.Column('source', sa.VARCHAR(length=16), nullable=False),
    sa.Column('memo', sa.TEXT(), nullable=True),
    sa.Column('started_at', sa.DATETIME(), nullable=False),
    sa.Column('ended_at', sa.DATETIME(), nullable=True),
    sa.Column('window_started_at', sa.DATETIME(), nullable=False),
    sa.Column('window_ended_at', sa.DATETIME(), nullable=False),
    sa.Column('carved_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('time_entry_carvings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_time_entry_carvings_user_id_window'), ['user_id', 'window_started_at'], unique=False)

    op.create_table('auto_time_entry_receipts',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('client_ref', sa.VARCHAR(length=64), nullable=False),
    sa.Column('mode', sa.VARCHAR(length=16), nullable=False),
    sa.Column('received_at', sa.DATETIME(), nullable=False),
    sa.Column('started_at', sa.DATETIME(), nullable=True),
    sa.Column('ended_at', sa.DATETIME(), nullable=True),
    sa.Column('task_id', _ID, nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'client_ref', name=op.f('uq_auto_time_entry_receipts_client_ref')),
    sqlite_autoincrement=True,
    )
    op.create_table('work_breaks',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('started_at', sa.DATETIME(), nullable=False),
    sa.Column('ended_at', sa.DATETIME(), nullable=False),
    sa.Column('source', sa.VARCHAR(length=16), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('work_breaks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_work_breaks_user_id_started_at'), ['user_id', 'started_at'], unique=False)

    op.create_table('pc_activity_days',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('local_date', sa.DATE(), nullable=False),
    sa.Column('time_zone', sa.VARCHAR(length=64), nullable=False),
    sa.Column('starts_at', sa.DATETIME(), nullable=False),
    sa.Column('ends_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'local_date', name=op.f('uq_pc_activity_days_user_date')),
    sqlite_autoincrement=True,
    )
    op.create_table('pc_activity_spans',
    sa.Column('id', _ID, nullable=False),
    sa.Column('day_id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('started_at', sa.DATETIME(), nullable=False),
    sa.Column('ended_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['day_id'], ['pc_activity_days.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('pc_activity_spans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pc_activity_spans_user_id_started_at'), ['user_id', 'started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_pc_activity_spans_day_id'), ['day_id'], unique=False)

    op.create_table('tracking_rules',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('position', sa.INTEGER(), nullable=False),
    sa.Column('app', sa.VARCHAR(length=260), nullable=True),
    sa.Column('title_contains', sa.VARCHAR(length=200), nullable=True),
    sa.Column('task_id', _ID, nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('tracking_rules', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tracking_rules_user_id_position'), ['user_id', 'position'], unique=False)

    op.create_table('tracking_rule_books',
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('changed_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('calendars',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('kind', sa.VARCHAR(length=16), nullable=False),
    sa.Column('name', sa.VARCHAR(length=200), nullable=False),
    sa.Column('color_key', sa.VARCHAR(length=16), nullable=False),
    sa.Column('sort_order', sa.INTEGER(), nullable=False),
    sa.Column('is_default', sa.BOOLEAN(), nullable=False),
    sa.Column('is_visible', sa.BOOLEAN(), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.Column('workdays', sa.VARCHAR(length=32), nullable=True),
    sa.Column('day_off_reason', sa.VARCHAR(length=16), nullable=True),
    sa.Column('counts_as_day_off', sa.BOOLEAN(), server_default=sa.text('0'), nullable=False),
    sa.Column('scope', sa.VARCHAR(length=16), server_default=sa.text("'WORK'"), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calendars', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendars_user_id'), ['user_id'], unique=False)

    op.create_table('calendar_days_off',
    sa.Column('id', _ID, nullable=False),
    sa.Column('calendar_id', _ID, nullable=False),
    sa.Column('day', sa.DATE(), nullable=False),
    sa.Column('name', sa.VARCHAR(length=200), nullable=True),
    sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('calendar_id', 'day', name=op.f('uq_calendar_days_off_day'))
    )
    op.create_table('calendar_imports',
    sa.Column('calendar_id', _ID, nullable=False),
    sa.Column('source', sa.VARCHAR(length=8), nullable=False),
    sa.Column('imported_at', sa.DATETIME(), nullable=False),
    sa.Column('event_count', sa.INTEGER(), nullable=False),
    sa.Column('feed_url_sealed', sa.TEXT(), nullable=True),
    sa.Column('feed_url_hint', sa.VARCHAR(length=300), nullable=True),
    sa.Column('last_attempt_at', sa.DATETIME(), nullable=True),
    sa.Column('last_error', sa.VARCHAR(length=64), nullable=True),
    sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('calendar_id')
    )
    op.create_table('calendar_imported_occurrences',
    sa.Column('id', _ID, nullable=False),
    sa.Column('calendar_id', _ID, nullable=False),
    sa.Column('title', sa.VARCHAR(length=500), nullable=False),
    sa.Column('location', sa.VARCHAR(length=500), nullable=True),
    sa.Column('start_utc', sa.DATETIME(), nullable=True),
    sa.Column('end_utc', sa.DATETIME(), nullable=True),
    sa.Column('start_date', sa.DATE(), nullable=True),
    sa.Column('end_date', sa.DATE(), nullable=True),
    sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('calendar_imported_occurrences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_imported_occurrences_calendar_id'), ['calendar_id'], unique=False)

    op.create_table('calendar_view_presets',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('name', sa.VARCHAR(length=200), nullable=False),
    sa.Column('calendar_ids', sa.TEXT(), nullable=False),
    sa.Column('sort_order', sa.INTEGER(), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('calendar_view_presets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_view_presets_user_id'), ['user_id'], unique=False)

    op.create_table('calendar_events',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('kind', sa.VARCHAR(length=16), nullable=False),
    sa.Column('title', sa.VARCHAR(length=500), nullable=False),
    sa.Column('time_zone', sa.VARCHAR(length=64), nullable=False),
    sa.Column('start_utc', sa.DATETIME(), nullable=False),
    sa.Column('duration_minutes', sa.INTEGER(), nullable=False),
    sa.Column('recurrence_rule', sa.TEXT(), nullable=True),
    sa.Column('location', sa.VARCHAR(length=500), nullable=True),
    sa.Column('description', sa.TEXT(), nullable=True),
    sa.Column('color_key', sa.VARCHAR(length=16), nullable=False),
    sa.Column('task_id', _ID, nullable=True),
    sa.Column('span_start_day', sa.INTEGER(), nullable=False),
    sa.Column('span_end_day', sa.INTEGER(), nullable=False),
    sa.Column('version', sa.INTEGER(), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.Column('alarm_enabled', sa.BOOLEAN(), nullable=True),
    sa.Column('alarm_15_min', sa.BOOLEAN(), server_default=sa.text('0'), nullable=False),
    sa.Column('alarm_5_min', sa.BOOLEAN(), server_default=sa.text('0'), nullable=False),
    sa.Column('alarm_1_min', sa.BOOLEAN(), server_default=sa.text('0'), nullable=False),
    sa.Column('alarm_at_start', sa.BOOLEAN(), server_default=sa.text('0'), nullable=False),
    sa.Column('event_type', sa.VARCHAR(length=16), server_default=sa.text("'EVENT'"), nullable=False),
    sa.Column('calendar_id', _ID, nullable=False),
    sa.ForeignKeyConstraint(['calendar_id'], ['calendars.id'], name=op.f('fk_calendar_events_calendar_id')),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('calendar_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calendar_events_user_span'), ['user_id', 'span_start_day', 'span_end_day'], unique=False)
        batch_op.create_index(batch_op.f('ix_calendar_events_task_id'), ['task_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calendar_events_calendar_id'), ['calendar_id'], unique=False)

    op.create_table('calendar_event_exceptions',
    sa.Column('id', _ID, nullable=False),
    sa.Column('event_id', _ID, nullable=False),
    sa.Column('occurrence_date', sa.DATE(), nullable=False),
    sa.Column('occurrence_time', sa.TIME(), nullable=True),
    sa.Column('type', sa.VARCHAR(length=16), nullable=False),
    sa.Column('override_title', sa.VARCHAR(length=500), nullable=True),
    sa.Column('override_location', sa.VARCHAR(length=500), nullable=True),
    sa.Column('override_start_time', sa.TIME(), nullable=True),
    sa.Column('override_duration_minutes', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['calendar_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'occurrence_date', 'occurrence_time', name=op.f('uq_calendar_event_exceptions_occurrence'))
    )
    op.create_table('calendar_event_moves',
    sa.Column('id', _ID, nullable=False),
    sa.Column('event_id', _ID, nullable=False),
    sa.Column('occurrence_date', sa.DATE(), nullable=False),
    sa.Column('occurrence_time', sa.TIME(), nullable=True),
    sa.Column('new_date', sa.DATE(), nullable=False),
    sa.Column('new_start_time', sa.TIME(), nullable=True),
    sa.Column('new_duration_minutes', sa.INTEGER(), nullable=True),
    sa.Column('title', sa.VARCHAR(length=500), nullable=True),
    sa.Column('location', sa.VARCHAR(length=500), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['calendar_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'occurrence_date', 'occurrence_time', name=op.f('uq_calendar_event_moves_occurrence'))
    )
    op.create_table('calendar_event_completions',
    sa.Column('id', _ID, nullable=False),
    sa.Column('event_id', _ID, nullable=False),
    sa.Column('occurrence_date', sa.DATE(), nullable=True),
    sa.Column('occurrence_time', sa.TIME(), nullable=True),
    sa.Column('completed_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['event_id'], ['calendar_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'occurrence_date', 'occurrence_time', name=op.f('uq_calendar_event_completions_occurrence'))
    )
    op.create_table('push_subscriptions',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('endpoint', sa.TEXT(), nullable=False),
    sa.Column('endpoint_hash', sa.VARCHAR(length=64), nullable=False),
    sa.Column('p256dh', sa.VARCHAR(length=128), nullable=False),
    sa.Column('auth', sa.VARCHAR(length=64), nullable=False),
    sa.Column('label', sa.VARCHAR(length=100), nullable=False),
    sa.Column('receives_calendar', sa.BOOLEAN(), nullable=False),
    sa.Column('created_at', sa.DATETIME(), nullable=False),
    sa.Column('last_sent_at', sa.DATETIME(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('endpoint_hash', name=op.f('uq_push_subscriptions_endpoint_hash')),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscriptions_user_id'), ['user_id'], unique=False)

    op.create_table('push_preferences',
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('event_alarm', sa.BOOLEAN(), nullable=False),
    sa.Column('routine_start', sa.BOOLEAN(), nullable=False),
    sa.Column('timer_left_running', sa.BOOLEAN(), nullable=False),
    sa.Column('closing_due', sa.BOOLEAN(), nullable=False),
    sa.Column('timer_left_running_hours', sa.INTEGER(), nullable=False),
    sa.Column('updated_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('push_dispatches',
    sa.Column('id', _ID, nullable=False),
    sa.Column('user_id', _ID, nullable=False),
    sa.Column('kind', sa.VARCHAR(length=32), nullable=False),
    sa.Column('notice_key', sa.VARCHAR(length=200), nullable=False),
    sa.Column('sent_at', sa.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'kind', 'notice_key', name=op.f('uq_push_dispatches_notice')),
    sqlite_autoincrement=True,
    )
    with op.batch_alter_table('push_dispatches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_dispatches_sent_at'), ['sent_at'], unique=False)
    with op.batch_alter_table("work_logs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("closing_period_id", _ID, nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_work_logs_closing_period_id"), "closing_periods", ["closing_period_id"], ["id"]
        )
        batch_op.create_index(batch_op.f("ix_work_logs_closing_period_id"), ["closing_period_id"], unique=False)
