"""休日カレンダーの初期名を直す（task #310）

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-07

「会社の公休」→「会社の休日」、「私の休み」→「個人の休日」。利用者が付け直した名前は変えない
（初期名のままの行だけを直す）。下げると初期名のままの行を元の名前へ戻す。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# （理由, 前の名前, 新しい名前）
RENAMES = (
    ("COMPANY", "会社の公休", "会社の休日"),
    ("PERSONAL", "私の休み", "個人の休日"),
)

_calendars = sa.table(
    "calendars",
    sa.column("kind", sa.String()),
    sa.column("name", sa.String()),
    sa.column("day_off_reason", sa.String()),
)


def _rename(reason: str, current: str, new: str) -> None:
    op.execute(
        _calendars.update()
        .where(
            _calendars.c.kind == "DAYS_OFF",
            _calendars.c.day_off_reason == reason,
            _calendars.c.name == current,
        )
        .values(name=new)
    )


def upgrade() -> None:
    for reason, old, new in RENAMES:
        _rename(reason, old, new)


def downgrade() -> None:
    for reason, old, new in RENAMES:
        _rename(reason, new, old)
