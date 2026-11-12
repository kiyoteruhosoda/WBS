"""Add the received interval to auto_time_entry_receipts (extending WinTrack clock-ins, task #400 / ADR-0050)

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-16

When an interval with the same ``client_ref`` arrives with only a later end, the clock-in is extended by the difference. For that, the receipt keeps
the received start, end and task. Existing receipts are empty (not extended; treated as a plain resend as before).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("auto_time_entry_receipts") as batch:
        batch.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("ended_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("task_id", _id(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("auto_time_entry_receipts") as batch:
        batch.drop_column("task_id")
        batch.drop_column("ended_at")
        batch.drop_column("started_at")
