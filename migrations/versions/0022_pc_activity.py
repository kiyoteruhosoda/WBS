"""pc_activity: PC を使っていた時間（WinTrack、task #397 / ADR-0049）

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-15

日（送り手のタイムゾーンでの日付）ごとの行と、その日の区間。打刻・実績・締めには使わない。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "pc_activity_days",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_pc_activity_days_user_date"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "pc_activity_spans",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("day_id", _id(), nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["day_id"], ["pc_activity_days.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_pc_activity_spans_user_id_started_at", "pc_activity_spans", ["user_id", "started_at"]
    )
    op.create_index("ix_pc_activity_spans_day_id", "pc_activity_spans", ["day_id"])


def downgrade() -> None:
    op.drop_index("ix_pc_activity_spans_day_id", table_name="pc_activity_spans")
    op.drop_index("ix_pc_activity_spans_user_id_started_at", table_name="pc_activity_spans")
    op.drop_table("pc_activity_spans")
    op.drop_table("pc_activity_days")
