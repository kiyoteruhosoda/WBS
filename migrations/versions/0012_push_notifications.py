"""端末への通知（Web Push）: 購読・種類の設定・送った記録（task #193 / ADR-0031）

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-02

- ``push_subscriptions``: ブラウザ・PWA の購読（端末 1 台ぶん）。一意は ``endpoint_hash``（sha256）
- ``push_preferences``: 利用者ごとの種類の入り / 切り（行が無い = 既定。すべて入り）
- ``push_dispatches``: 送った通知の記録。``(user_id, kind, notice_key)`` が一意
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("endpoint_hash", sa.String(length=64), nullable=False),
        sa.Column("p256dh", sa.String(length=128), nullable=False),
        sa.Column("auth", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("receives_calendar", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_hash", name="uq_push_subscriptions_endpoint_hash"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    op.create_table(
        "push_preferences",
        sa.Column("user_id", _id(), autoincrement=False, nullable=False),
        sa.Column("event_alarm", sa.Boolean(), nullable=False),
        sa.Column("routine_start", sa.Boolean(), nullable=False),
        sa.Column("timer_left_running", sa.Boolean(), nullable=False),
        sa.Column("closing_due", sa.Boolean(), nullable=False),
        sa.Column("timer_left_running_hours", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "push_dispatches",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("notice_key", sa.String(length=200), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "notice_key", name="uq_push_dispatches_notice"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_push_dispatches_sent_at", "push_dispatches", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_push_dispatches_sent_at", table_name="push_dispatches")
    op.drop_table("push_dispatches")
    op.drop_table("push_preferences")
    op.drop_index("ix_push_subscriptions_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
