"""projects.code: 任意のプロジェクトコード（task #187）

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-02

- ``projects.code``: 任意の短い文字列（32 字まで）。プロジェクト一覧で名前の横に出すだけ。
  一意にはしない。**既存のプロジェクトは NULL**（コード無し）。
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
