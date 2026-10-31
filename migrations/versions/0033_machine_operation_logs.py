"""機械が書いた操作の記録の表を足す（task #802 / ADR-0068）

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-31

戻すと表ごと消える（記録だけの表で、ほかの表からは参照しない）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machine_operation_logs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column(
            "user_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.String(length=255), nullable=True),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_machine_operation_logs_occurred_at", "machine_operation_logs", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_machine_operation_logs_occurred_at", table_name="machine_operation_logs")
    op.drop_table("machine_operation_logs")
