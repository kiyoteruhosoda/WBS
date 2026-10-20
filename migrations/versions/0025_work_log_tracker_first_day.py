"""work_logs.tracker_first_day: Tracker で締めた時間を受け取る（task #540 / ADR-0056）

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-20

Tracker から受け取った行（``source=tracker``）は、Tracker の締めの期間（利用者 × 初日）ごとに置き換え、取り消しで消す。
今までの行は空（手で書いた行・WBS 自身の締めの行）。
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
