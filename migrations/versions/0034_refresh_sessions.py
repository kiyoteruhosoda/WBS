"""Add the per-sign-in record refresh_sessions and drop auth_sessions (task #819 / ADR-0069)

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-02

⚠ The contents of auth_sessions (active sessions) are discarded. Right after deploy everyone signs in once more (the owner agreed).
Downgrading does not restore the contents (an empty table is created; everyone signs in once more).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("user_id", _ID, nullable=False),
        sa.Column("current_jti", sa.String(length=32), nullable=False),
        sa.Column("previous_jti", sa.String(length=32), nullable=True),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("idp_session_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_sessions_expires_at"), "refresh_sessions", ["expires_at"], unique=False)
    op.create_index(
        op.f("ix_refresh_sessions_idp_session_id"), "refresh_sessions", ["idp_session_id"], unique=False
    )
    op.create_index(op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"], unique=False)
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_idp_session_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_expires_at"), table_name="auth_sessions")
    op.drop_table("auth_sessions")


def downgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", _ID, autoincrement=True, nullable=False),
        sa.Column("user_id", _ID, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("idp_session_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_expires_at"), "auth_sessions", ["expires_at"], unique=False)
    op.create_index(
        op.f("ix_auth_sessions_idp_session_id"), "auth_sessions", ["idp_session_id"], unique=False
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.drop_index(op.f("ix_refresh_sessions_user_id"), table_name="refresh_sessions")
    op.drop_index(op.f("ix_refresh_sessions_idp_session_id"), table_name="refresh_sessions")
    op.drop_index(op.f("ix_refresh_sessions_expires_at"), table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
