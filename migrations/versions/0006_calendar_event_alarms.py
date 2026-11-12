"""Notification columns of calendar_events (task #183 / ADR-0021)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

Brings NolumiaScheduler's ``EventAlarm`` back to events. Rows with NULL ``alarm_enabled`` "have no notification".
**Existing events have no notification** (``alarm_enabled`` is NULL, the 4 columns are false). The default for new events
(all 4 on) is applied at the creation entry point (application layer).
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
