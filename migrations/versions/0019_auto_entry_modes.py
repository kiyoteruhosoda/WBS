"""How automatic clock-ins are sent (fill / override), plus receipt records and carve-out records (WinTrack, task #386 / ADR-0045)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-13

- ``time_entries``: drop the ``(user_id, client_ref)`` uniqueness for a plain index (``fill`` can produce several entries from one ID).
  Add ``auto_mode``. Existing automatic clock-ins are treated as ``fill`` (sent before the mode could be chosen)
- ``auto_time_entry_receipts``: records of received IDs. Resend detection is guarded by uniqueness on ``(user_id, client_ref)``.
  Built from the IDs of existing automatic clock-ins
- ``time_entry_carvings``: the pre-carving state of manual clock-ins carved out by exception work

⚠ Downgrading fails when two or more automatic clock-ins share an ID, since the unique index cannot be created (clean up before downgrading).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.drop_index("uq_time_entries_client_ref_per_user", table_name="time_entries")
    op.create_index("ix_time_entries_user_id_client_ref", "time_entries", ["user_id", "client_ref"])
    with op.batch_alter_table("time_entries") as batch:
        batch.add_column(sa.Column("auto_mode", sa.String(length=16), nullable=True))
    op.execute("UPDATE time_entries SET auto_mode = 'fill' WHERE source = 'auto'")

    op.create_table(
        "auto_time_entry_receipts",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("client_ref", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_ref", name="uq_auto_time_entry_receipts_client_ref"),
        sqlite_autoincrement=True,
    )
    op.execute(
        "INSERT INTO auto_time_entry_receipts (user_id, client_ref, mode, received_at)"
        " SELECT user_id, client_ref, 'fill', MIN(created_at) FROM time_entries"
        " WHERE source = 'auto' AND client_ref IS NOT NULL GROUP BY user_id, client_ref"
    )

    op.create_table(
        "time_entry_carvings",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("client_ref", sa.String(length=64), nullable=False),
        sa.Column("time_entry_id", _id(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("task_id", _id(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("window_started_at", sa.DateTime(), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(), nullable=False),
        sa.Column("carved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_time_entry_carvings_user_id_window",
        "time_entry_carvings",
        ["user_id", "window_started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_time_entry_carvings_user_id_window", table_name="time_entry_carvings")
    op.drop_table("time_entry_carvings")
    op.drop_table("auto_time_entry_receipts")
    with op.batch_alter_table("time_entries") as batch:
        batch.drop_column("auto_mode")
    op.drop_index("ix_time_entries_user_id_client_ref", table_name="time_entries")
    op.create_index(
        "uq_time_entries_client_ref_per_user", "time_entries", ["user_id", "client_ref"], unique=True
    )
