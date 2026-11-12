"""Multiple event calendars and view combinations (task #191 / ADR-0027)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02

- Table ``calendars``: per-user event calendars (name, color, order, visible, default)
- Table ``calendar_view_presets``: view combinations (name + JSON of the ids of calendars to show)
- ``calendar_events.calendar_id``: the calendar an event belongs to (required)

⚠ **Creates one default calendar "予定" (Events) per user and puts all existing events in it.**
Downgrading drops the calendars table and the events' ``calendar_id`` (the events themselves remain).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CALENDAR_NAME = "予定"
# ⚠ calendar_events is a table that does not reuse deleted event ids (sqlite_autoincrement). When SQLite
#   rebuilds the table (column NOT NULL, foreign keys), pass it to the rebuild too so it is not dropped.
_EVENTS_TABLE_KWARGS = {"sqlite_autoincrement": True}


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _events_sequence() -> int | None:
    """The max calendar_events sequence value SQLite remembers (so a rebuild does not fall back to the max row id)."""
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return None
    return bind.exec_driver_sql(
        "SELECT seq FROM sqlite_sequence WHERE name = 'calendar_events'"
    ).scalar()


def _restore_events_sequence(seq: int | None) -> None:
    if seq is None:
        return
    bind = op.get_bind()
    updated = bind.exec_driver_sql(
        "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'calendar_events'", (seq,)
    ).rowcount
    if not updated:
        bind.exec_driver_sql(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('calendar_events', ?)", (seq,)
        )


def upgrade() -> None:
    # ⚠ Read before the rebuild (even a rebuild that only adds a column falls back to the max row id).
    seq = _events_sequence()
    op.create_table(
        "calendars",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("color_key", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_calendars_user_id", "calendars", ["user_id"], unique=False)
    op.create_table(
        "calendar_view_presets",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("calendar_ids", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_calendar_view_presets_user_id", "calendar_view_presets", ["user_id"], unique=False
    )

    # One default calendar per user.
    users = sa.table("users", sa.column("id", _id()))
    calendars = sa.table(
        "calendars",
        sa.column("user_id", _id()),
        sa.column("kind", sa.String()),
        sa.column("name", sa.String()),
        sa.column("color_key", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_visible", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
        sa.column("id", _id()),
    )
    now = sa.func.current_timestamp()
    op.execute(
        calendars.insert().from_select(
            [
                "user_id", "kind", "name", "color_key", "sort_order",
                "is_default", "is_visible", "created_at", "updated_at",
            ],
            sa.select(
                users.c.id,
                sa.literal("EVENTS"),
                sa.literal(DEFAULT_CALENDAR_NAME),
                sa.literal("DEFAULT"),
                sa.literal(0),
                sa.true(),
                sa.true(),
                now,
                now,
            ),
        )
    )

    with op.batch_alter_table("calendar_events", table_kwargs=_EVENTS_TABLE_KWARGS) as batch:
        batch.add_column(sa.Column("calendar_id", _id(), nullable=True))
    _restore_events_sequence(seq)

    events = sa.table(
        "calendar_events", sa.column("user_id", _id()), sa.column("calendar_id", _id())
    )
    op.execute(
        events.update().values(
            calendar_id=sa.select(calendars.c.id)
            .where(calendars.c.user_id == events.c.user_id, calendars.c.is_default == sa.true())
            .scalar_subquery()
        )
    )

    with op.batch_alter_table("calendar_events", table_kwargs=_EVENTS_TABLE_KWARGS) as batch:
        batch.alter_column("calendar_id", existing_type=_id(), nullable=False)
        batch.create_foreign_key(
            "fk_calendar_events_calendar_id", "calendars", ["calendar_id"], ["id"]
        )
        batch.create_index("ix_calendar_events_calendar_id", ["calendar_id"], unique=False)
    _restore_events_sequence(seq)


def downgrade() -> None:
    seq = _events_sequence()
    with op.batch_alter_table("calendar_events", table_kwargs=_EVENTS_TABLE_KWARGS) as batch:
        batch.drop_index("ix_calendar_events_calendar_id")
        batch.drop_constraint("fk_calendar_events_calendar_id", type_="foreignkey")
        batch.drop_column("calendar_id")
    _restore_events_sequence(seq)
    op.drop_index("ix_calendar_view_presets_user_id", table_name="calendar_view_presets")
    op.drop_table("calendar_view_presets")
    op.drop_index("ix_calendars_user_id", table_name="calendars")
    op.drop_table("calendars")
