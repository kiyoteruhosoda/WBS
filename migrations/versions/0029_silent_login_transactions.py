"""ログインの往復に「黙って確かめる」印を足す（task #647 / ADR-0062）

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-22

- ``auth_login_transactions`` に ``silent``（``prompt=none`` で送り出した往復か）を足す

今の行は偽（ふつうの往復）になる。行は 10 分で使い切る一時データなので、戻すと列が消えるだけ。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("auth_login_transactions") as batch:
        batch.add_column(
            sa.Column("silent", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("auth_login_transactions") as batch:
        batch.drop_column("silent")
