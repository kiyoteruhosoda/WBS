"""time_entries.client_ref: 自動の打刻の送り直しを見分ける（WinTrack、task #379 / ADR-0042）

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-13

PC の自動記録（WinTrack）は打刻ごとに ID（UUID）を付けて送る。同じ利用者・同じ ID は 1 本だけ
（``uq_time_entries_client_ref_per_user``）。手の打刻は NULL のままで、NULL どうしはぶつからない。
出どころ ``auto`` は ``source`` の文字列が 1 つ増えるだけなので、表は変えない。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("time_entries") as batch:
        batch.add_column(sa.Column("client_ref", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_time_entries_client_ref_per_user",
        "time_entries",
        ["user_id", "client_ref"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_time_entries_client_ref_per_user", table_name="time_entries")
    with op.batch_alter_table("time_entries") as batch:
        batch.drop_column("client_ref")
