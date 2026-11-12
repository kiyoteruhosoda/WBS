"""Add the flag for people who can create top-level projects (task #734 / ADR-0065)

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-30

- Add ``can_create_projects`` (whether the user can create top-level projects) to ``users``
- True for current admins of a top-level project and for the default user (id=1, the single user of deployments without SSO).
  False for everyone else (only top-level creation is blocked; inside trees they are members of, they can create as before)

Downgrading just drops the column (back to the original form where anyone can create).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("can_create_projects", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        "UPDATE users SET can_create_projects = 1 WHERE id = 1 OR id IN ("
        " SELECT m.user_id FROM project_members m"
        " JOIN projects p ON p.id = m.project_id"
        " WHERE p.parent_project_id IS NULL AND m.role = 'manager')"
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("can_create_projects")
