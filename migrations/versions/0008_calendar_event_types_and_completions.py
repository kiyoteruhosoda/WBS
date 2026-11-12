"""Event kinds (event / task) and "done" for task occurrences (task #190 / ADR-0025)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01

- ``calendar_events.event_type``: ``EVENT`` (event) / ``TASK`` (task). **Existing events are EVENT**.
- ``calendar_event_completions``: done marks for occurrences of task-kind events. An occurrence is (candidate date, series start time);
  one-off events have both NULL. Deleted together with the event.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch:
        batch.add_column(
            sa.Column("event_type", sa.String(length=16), server_default="EVENT", nullable=False)
        )
    op.create_table(
        "calendar_event_completions",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("event_id", _id(), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=True),
        sa.Column("occurrence_time", sa.Time(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["calendar_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_completions_occurrence",
        ),
    )


def downgrade() -> None:
    op.drop_table("calendar_event_completions")
    with op.batch_alter_table("calendar_events") as batch:
        batch.drop_column("event_type")
