"""予定（calendar_events と例外・移動）と営業日カレンダー（business_calendars と祝日）

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

task #156 の第 2 段（ADR-0009）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("start_utc", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color_key", sa.String(length=16), nullable=False),
        sa.Column("task_id", _id(), nullable=True),
        sa.Column("span_start_day", sa.Integer(), nullable=False),
        sa.Column("span_end_day", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # 消した id を使い回さない（古い画面が同じ id の別の予定を直さないように）
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_calendar_events_user_span",
        "calendar_events",
        ["user_id", "span_start_day", "span_end_day"],
        unique=False,
    )
    op.create_index("ix_calendar_events_task_id", "calendar_events", ["task_id"], unique=False)

    op.create_table(
        "calendar_event_exceptions",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("event_id", _id(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("occurrence_time", sa.Time(), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("override_title", sa.String(length=500), nullable=True),
        sa.Column("override_location", sa.String(length=500), nullable=True),
        sa.Column("override_start_time", sa.Time(), nullable=True),
        sa.Column("override_duration_minutes", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["calendar_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_exceptions_occurrence",
        ),
    )
    op.create_table(
        "calendar_event_moves",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("event_id", _id(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("occurrence_time", sa.Time(), nullable=True),
        sa.Column("new_date", sa.Date(), nullable=False),
        sa.Column("new_start_time", sa.Time(), nullable=True),
        sa.Column("new_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["calendar_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_moves_occurrence",
        ),
    )

    op.create_table(
        "business_calendars",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("workdays", sa.String(length=32), nullable=False),
        sa.Column("shift_on_holidays_only", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_business_calendars_user_id", "business_calendars", ["user_id"], unique=False
    )
    op.create_table(
        "business_calendar_holidays",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("calendar_id", _id(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "calendar_id", "holiday_date", name="uq_business_calendar_holidays_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("business_calendar_holidays")
    op.drop_index("ix_business_calendars_user_id", table_name="business_calendars")
    op.drop_table("business_calendars")
    op.drop_table("calendar_event_moves")
    op.drop_table("calendar_event_exceptions")
    op.drop_index("ix_calendar_events_task_id", table_name="calendar_events")
    op.drop_index("ix_calendar_events_user_span", table_name="calendar_events")
    op.drop_table("calendar_events")
