"""closing_periods: 締めの確定（task #161 / ADR-0012）と、work_logs の出どころの列

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

- 表 ``closing_periods``: 確定した期間（行がある = 確定済み）。``(user_id, first_day)`` で一意
- ``work_logs`` に ``source``（``manual`` / ``closing``、既存の行は ``manual``）・
  ``closing_period_id``（締めで作った行がどの期間から来たか）・``duration_seconds``（正確な長さ）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "closing_periods",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("last_day", sa.Date(), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "first_day", name="uq_closing_periods_user_first_day"),
        # 開け直すと行を消す。消した id を使い回さない
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("work_logs") as batch:
        batch.add_column(
            sa.Column(
                "source", sa.String(length=16), server_default=sa.text("'manual'"), nullable=False
            )
        )
        batch.add_column(sa.Column("closing_period_id", _id(), nullable=True))
        batch.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_work_logs_closing_period_id", "closing_periods", ["closing_period_id"], ["id"]
        )
        batch.create_index("ix_work_logs_closing_period_id", ["closing_period_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("work_logs") as batch:
        batch.drop_index("ix_work_logs_closing_period_id")
        batch.drop_constraint("fk_work_logs_closing_period_id", type_="foreignkey")
        batch.drop_column("duration_seconds")
        batch.drop_column("closing_period_id")
        batch.drop_column("source")
    op.drop_table("closing_periods")
