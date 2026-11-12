"""Imported calendars (reading external iCalendar feeds) (task #196 / ADR-0037)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-02

- Table ``calendar_imports``: fetch state of an imported calendar (one row per calendar; the subscribed
  URL is sealed)
- Table ``calendar_imported_occurrences``: fetched occurrences (replaced per calendar on every fetch)

The calendar kind ``IMPORTED`` only adds a value to ``calendars.kind`` (a string); columns do not change.
Downgrading drops both tables along with the imported calendars' rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "calendar_imports",
        sa.Column("calendar_id", _id(), autoincrement=False, nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("feed_url_sealed", sa.Text(), nullable=True),
        sa.Column("feed_url_hint", sa.String(length=300), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("calendar_id"),
    )
    op.create_table(
        "calendar_imported_occurrences",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("calendar_id", _id(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("start_utc", sa.DateTime(), nullable=True),
        sa.Column("end_utc", sa.DateTime(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calendar_imported_occurrences_calendar_id",
        "calendar_imported_occurrences",
        ["calendar_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calendar_imported_occurrences_calendar_id", table_name="calendar_imported_occurrences"
    )
    op.drop_table("calendar_imported_occurrences")
    op.drop_table("calendar_imports")
    op.execute(sa.text("DELETE FROM calendars WHERE kind = 'IMPORTED'"))
