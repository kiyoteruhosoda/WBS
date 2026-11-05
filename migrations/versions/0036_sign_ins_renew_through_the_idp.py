"""ログインの控えから振り替えの列を外し、往復に「続ける」の項目を足す（task #889 / ADR-0071）

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-05

- refresh_sessions: current_jti・previous_jti・rotated_at を消す（リフレッシュトークンをもう出さない）。
  行（ログインの控え）は残す。今のログインはそのまま続く
- auth_login_transactions: purpose（login / renew）・continued_user_id・continued_session_id を足す

戻すと current_jti は空の値で埋まる（その控えの古いリフレッシュトークンは通らない。入り直しになる）。
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
    # SQLite は列を消せないので、表を作り直す（batch）
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
