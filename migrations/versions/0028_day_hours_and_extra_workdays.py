"""その日の稼働時間（残業・短い日・休日出勤）と、プロジェクトの稼働日（task #558 / ADR-0060）

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-20

- 各人の休み（``member_days_off``）に ``hours`` を足す。入っていれば、その日の稼働時間（休む割合は見ない）
- 表 ``team_extra_workdays``: 稼働しない曜日に働く日（プロジェクトごと。下のプロジェクトは引き継ぐ）

今の行は ``hours`` が空（今までどおり休む割合）になる。戻すと列と表が消える。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("member_days_off") as batch:
        batch.add_column(sa.Column("hours", sa.Numeric(4, 2), nullable=True))
    op.create_table(
        "team_extra_workdays",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_team_extra_workdays_project_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "day", name="uq_team_extra_workdays_project_day"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("team_extra_workdays")
    with op.batch_alter_table("member_days_off") as batch:
        batch.drop_column("hours")
