"""tasks.archived_at: 打刻や実績のあるタスクは消さずに「しまう」（task #388 / ADR-0046）

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-13

しまったタスクは一覧と付け替え先に出ないが、実績と締めの表には名前ごと残る。いまあるタスクは NULL（しまっていない）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("archived_at")
