"""Add a "silent check" flag to the sign-in round trip (task #647 / ADR-0062)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-22

- Add ``silent`` (whether the round trip was sent with ``prompt=none``) to ``auth_login_transactions``

Existing rows become false (an ordinary round trip). Rows are temporary data used up within 10 minutes, so downgrading just drops the column.
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
