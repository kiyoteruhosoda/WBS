"""Event calendars get a "work / private" scope (task #191 / ADR-0033)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-02

- ``calendars.scope``: ``WORK`` / ``PRIVATE`` (required; default ``WORK``). All existing calendars (including the default calendar
  and day-off layers) become ``WORK``

Downgrading drops the column (calendars that were private go back to work).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("calendars") as batch:
        batch.add_column(
            sa.Column("scope", sa.String(length=16), server_default="WORK", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("calendars") as batch:
        batch.drop_column("scope")
