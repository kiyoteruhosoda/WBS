"""いちばん上のプロジェクトを作れる人の印を足す（task #734 / ADR-0065）

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-30

- ``users`` に ``can_create_projects``（いちばん上のプロジェクトを作れるか）を足す
- 今いちばん上のプロジェクトの管理者である人と、既定の利用者（id=1。SSO を使わない配備の 1 人）は真にする。
  ほかの人は偽（作れなくなるのはいちばん上だけで、メンバーになっている木の中では今までどおり作れる）

戻すと列が消えるだけ（だれでも作れる元の形に戻る）。
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
