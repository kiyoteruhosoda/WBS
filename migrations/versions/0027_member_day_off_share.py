"""Add the share of the day taken off to personal days off (full day 100, half day 50. task #557 / ADR-0059)

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-20

Existing rows become full days (100). Downgrading drops the column (half days remain as full days off).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("member_days_off") as batch:
        batch.add_column(sa.Column("off_percent", sa.Integer(), server_default="100", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("member_days_off") as batch:
        batch.drop_column("off_percent")
