"""メンバーの 1 日の工数・従事率、チームの稼働する曜日と休日、各人の休み、タスクのアサイン比率（task #554 / ADR-0058）

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-20

今の行は既定（8 時間・100%・月〜金・休みなし・比率なし）になる。戻すと表と列が消えて元どおり。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("project_members") as batch:
        batch.add_column(sa.Column("daily_hours", sa.Numeric(4, 2), server_default="8", nullable=False))
        batch.add_column(sa.Column("engagement_percent", sa.Integer(), server_default="100", nullable=False))
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("allocation_percent", sa.Integer(), nullable=True))
    op.create_table(
        "team_workweeks",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("workdays", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_team_workweeks_project_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_team_workweeks_project"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "team_days_off",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_team_days_off_project_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "day", name="uq_team_days_off_project_day"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "member_days_off",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_member_days_off_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", name="uq_member_days_off_user_day"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("member_days_off")
    op.drop_table("team_days_off")
    op.drop_table("team_workweeks")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("allocation_percent")
    with op.batch_alter_table("project_members") as batch:
        batch.drop_column("engagement_percent")
        batch.drop_column("daily_hours")
