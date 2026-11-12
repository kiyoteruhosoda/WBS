"""Drop the project-only actuals table (task #708 withdrawn / ADR-0064)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-29

- Drop ``project_work_logs``. #708 was withdrawn, so the receiving endpoint is gone (no rows were received)

Downgrading creates an empty table (same shape as 0030).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.drop_index("ix_project_work_logs_user_period", table_name="project_work_logs")
    op.drop_table("project_work_logs")


def downgrade() -> None:
    op.create_table(
        "project_work_logs",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("tracker_first_day", sa.Date(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_project_work_logs_user_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_work_logs_project_id"),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_project_work_logs_user_period", "project_work_logs", ["user_id", "tracker_first_day"]
    )
