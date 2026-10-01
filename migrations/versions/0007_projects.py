"""projects: 入れ子のプロジェクトと、タスク・マイルストーンの所属（task #187 / ADR-0024）

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

- 表 ``projects``: 利用者ごと。``parent_project_id`` で何段でも入れ子にできる（隣接リスト。
  環はアプリ側で断る）。名前・色・説明・状態（``active`` / ``archived``）・兄弟の中の並び
- ``tasks.project_id`` / ``milestones.project_id``: 空 = 未分類

⚠ **既存のタスクとマイルストーンは未分類のまま**（この移行はプロジェクトを 1 つも作らない）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("parent_project_id", _id(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["parent_project_id"], ["projects.id"], name="fk_projects_parent_project_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        # 消したプロジェクトの id を使い回さない（古い画面が、同じ id の別のプロジェクトへ書かないように）
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_projects_user_id_parent_project_id",
        "projects",
        ["user_id", "parent_project_id"],
        unique=False,
    )
    for table in ("tasks", "milestones"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("project_id", _id(), nullable=True))
            batch.create_foreign_key(f"fk_{table}_project_id", "projects", ["project_id"], ["id"])
            batch.create_index(f"ix_{table}_project_id", ["project_id"], unique=False)


def downgrade() -> None:
    for table in ("milestones", "tasks"):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f"ix_{table}_project_id")
            batch.drop_constraint(f"fk_{table}_project_id", type_="foreignkey")
            batch.drop_column("project_id")
    op.drop_index("ix_projects_user_id_parent_project_id", table_name="projects")
    op.drop_table("projects")
