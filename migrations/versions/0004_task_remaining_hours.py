"""tasks.remaining_hours: 手で持つ残（task #165 / ADR-0010）

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

進捗率を設計書 §5.1 の「実績 ÷（実績 ＋ 残）」に揃えるため、残を列で持つ。
既存の行は、それまで画面に出ていた残と同じ値で埋める:
DONE は 0、見積があれば max(見積 − 実績, 0)（実績は削除していない work_logs の合計）、
見積が空なら空のまま（判断材料が無い）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# MAX(a, b) / GREATEST は方言で名前が違うので CASE で書く（SQLite と MariaDB の両方で通る）。
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
