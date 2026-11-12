"""tasks.remaining_hours: manually held remaining hours (task #165 / ADR-0010)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

Remaining hours are held in a column so progress matches "actual / (actual + remaining)" from design doc §5.1.
Existing rows are filled with the same value the screen showed as remaining until now:
0 for DONE; max(estimate - actual, 0) if there is an estimate (actual is the sum of non-deleted work_logs);
left empty if there is no estimate (nothing to judge by).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MAX(a, b) / GREATEST are named differently per dialect, so use CASE (works on both SQLite and MariaDB).
_FILL_REMAINING = """
UPDATE tasks SET remaining_hours = CASE
    WHEN status = 'DONE' THEN 0
    WHEN estimated_hours IS NULL THEN NULL
    WHEN estimated_hours - (
        SELECT COALESCE(SUM(wl.hours), 0) FROM work_logs wl
        WHERE wl.task_id = tasks.id AND wl.deleted_at IS NULL
    ) > 0 THEN estimated_hours - (
        SELECT COALESCE(SUM(wl.hours), 0) FROM work_logs wl
        WHERE wl.task_id = tasks.id AND wl.deleted_at IS NULL
    )
    ELSE 0
END
"""


def upgrade() -> None:
    op.add_column("tasks", sa.Column("remaining_hours", sa.Numeric(6, 2), nullable=True))
    op.execute(_FILL_REMAINING)


def downgrade() -> None:
    op.drop_column("tasks", "remaining_hours")
