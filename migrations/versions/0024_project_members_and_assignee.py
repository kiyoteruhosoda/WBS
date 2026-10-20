"""project_members と tasks.assignee_user_id: プロジェクトを共有し、タスクに担当者を付ける（task #544 / ADR-0055）

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-20

メンバーはいちばん上のプロジェクトにだけ置く。今ある根のプロジェクトは作った人を管理者にし、
今あるタスクの担当者は作った人にする（消す・書き換えるものは無い）。戻すと表と列が消えて元どおり。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("project_id", _id(), nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_members_project_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_project_members_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_project_members_user_id", "project_members", ["user_id"])
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("assignee_user_id", _id(), nullable=True))
        batch.create_foreign_key("fk_tasks_assignee_user_id", "users", ["assignee_user_id"], ["id"])
        batch.create_index("ix_tasks_assignee_user_id", ["assignee_user_id"])

    # 今ある根のプロジェクトは作った人を管理者に、今あるタスクの担当者は作った人に（ADR-0055 決定 7）
    op.execute(
        "INSERT INTO project_members (project_id, user_id, role, created_at) "
        "SELECT id, user_id, 'manager', CURRENT_TIMESTAMP FROM projects WHERE parent_project_id IS NULL"
    )
    op.execute("UPDATE tasks SET assignee_user_id = user_id")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_assignee_user_id")
        batch.drop_constraint("fk_tasks_assignee_user_id", type_="foreignkey")
        batch.drop_column("assignee_user_id")
    op.drop_index("ix_project_members_user_id", table_name="project_members")
    op.drop_table("project_members")
