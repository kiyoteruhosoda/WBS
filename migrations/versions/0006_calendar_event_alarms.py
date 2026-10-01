"""calendar_events の通知の列（task #183 / ADR-0021）

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

NolumiaScheduler の ``EventAlarm`` を予定に戻す。``alarm_enabled`` が NULL の行は「通知を持たない」。
**既存の予定は通知なし**（``alarm_enabled`` は NULL、4 つの列は false）。新しい予定の既定
（4 つとも入り）は作る口（アプリケーション層）で付ける。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FLAGS = ("alarm_15_min", "alarm_5_min", "alarm_1_min", "alarm_at_start")


def upgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch:
        batch.add_column(sa.Column("alarm_enabled", sa.Boolean(), nullable=True))
        for name in _FLAGS:
            batch.add_column(
                sa.Column(name, sa.Boolean(), server_default=sa.false(), nullable=False)
            )


def downgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch:
        for name in reversed(_FLAGS):
            batch.drop_column(name)
        batch.drop_column("alarm_enabled")
