"""work_breaks: breaks (WinTrack, task #392 / ADR-0048)

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-13

Kept separately from clock-ins. The actual duration is the clock-in duration minus the break time overlapping that clock-in.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "work_breaks",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_work_breaks_user_id_started_at", "work_breaks", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_work_breaks_user_id_started_at", table_name="work_breaks")
    op.drop_table("work_breaks")
