"""projects.code: optional project code (task #187)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-02

- ``projects.code``: an optional short string (up to 32 characters). Only shown next to the name in the project list.
  Not unique. **Existing projects are NULL** (no code).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("code", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("code")
