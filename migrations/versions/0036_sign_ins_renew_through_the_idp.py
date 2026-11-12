"""Drop the rotation columns from the sign-in record and add "continue" fields to the round trip (task #889 / ADR-0071)

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-05

- refresh_sessions: drop current_jti, previous_jti, rotated_at (refresh tokens are no longer issued).
  Rows (sign-in records) are kept. Current sign-ins continue as they are
- auth_login_transactions: add purpose (login / renew), continued_user_id, continued_session_id

Downgrading fills current_jti with an empty value (that record's old refresh token no longer works; the user signs in again).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    # SQLite cannot drop columns, so the table is rebuilt (batch)
    with op.batch_alter_table("refresh_sessions") as batch:
        batch.drop_column("rotated_at")
        batch.drop_column("previous_jti")
        batch.drop_column("current_jti")
    with op.batch_alter_table("auth_login_transactions") as batch:
        batch.add_column(sa.Column("purpose", sa.String(length=16), nullable=False, server_default="login"))
        batch.add_column(sa.Column("continued_user_id", _ID, nullable=True))
        batch.add_column(sa.Column("continued_session_id", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("auth_login_transactions") as batch:
        batch.drop_column("continued_session_id")
        batch.drop_column("continued_user_id")
        batch.drop_column("purpose")
    with op.batch_alter_table("refresh_sessions") as batch:
        batch.add_column(sa.Column("current_jti", sa.String(length=32), nullable=False, server_default=""))
        batch.add_column(sa.Column("previous_jti", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("rotated_at", sa.DateTime(), nullable=True))
