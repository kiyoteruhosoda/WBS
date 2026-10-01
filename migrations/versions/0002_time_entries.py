"""time_entries: 打刻（Start / Stop のタイムトラッカー。task #154 / ADR-0008）

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01

走っている打刻（``ended_at`` が空）は 1 人 1 本を、部分一意索引
``uq_time_entries_running_per_user``（``WHERE ended_at IS NULL``）で守る。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "time_entries",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("task_id", _id(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_time_entries_running_per_user",
        "time_entries",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL"),
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_time_entries_user_id_started_at",
        "time_entries",
        ["user_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_time_entries_user_id_started_at", table_name="time_entries")
    op.drop_index("uq_time_entries_running_per_user", table_name="time_entries")
    op.drop_table("time_entries")
