"""work_logs.tracker_first_day: receive hours closed in Tracker (task #540 / ADR-0056)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-20

Rows received from Tracker (``source=tracker``) are replaced per Tracker closing period (user x first day) and deleted on cancellation.
Existing rows are empty (hand-written rows and rows from WBS's own closing).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_logs") as batch:
        batch.add_column(sa.Column("tracker_first_day", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_logs") as batch:
        batch.drop_column("tracker_first_day")
