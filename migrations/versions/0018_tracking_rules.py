"""tracking_rules: PC の自動記録の規則（WinTrack、task #381 / ADR-0043）

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13

- ``tracking_rules``: 「アプリが〜」「表題に〜を含む」→ タスク。``position`` の順に上から当てる（照合は PC の中）
- ``tracking_rule_books``: 利用者ごとに、規則を最後に変えた時刻（消したことも PC へ伝えるため）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "tracking_rules",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("app", sa.String(length=260), nullable=True),
        sa.Column("title_contains", sa.String(length=200), nullable=True),
        sa.Column("task_id", _id(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_tracking_rules_user_id_position", "tracking_rules", ["user_id", "position"]
    )
    op.create_table(
        "tracking_rule_books",
        sa.Column("user_id", _id(), autoincrement=False, nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("tracking_rule_books")
    op.drop_index("ix_tracking_rules_user_id_position", table_name="tracking_rules")
    op.drop_table("tracking_rules")
