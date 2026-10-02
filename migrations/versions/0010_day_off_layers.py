"""休みの 4 層（営業日・会社の公休・私の休み・日本の祝日）（task #191 / ADR-0029）

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02

- ``calendars`` に休みの層の列: ``workdays``（営業日の層の曜日）・``day_off_reason``（休みの日の
  一覧の層の理由）・``counts_as_day_off``（休みとして数える）
- 表 ``calendar_days_off``: 休みの日の一覧の層の日付（終日。名前は任意）

⚠ **利用者ごとに 4 つの層を作る。** 営業日の層の曜日は、その利用者のいちばん古い営業日カレンダー
（ADR-0009）のもの（無ければ月〜金）。**営業日カレンダーの祝日はすべて「日本の祝日」の層へ写す**
（同じ日は先に作ったカレンダーの名前）。営業日カレンダーの表はそのまま残す。
下げると層と日付は消える（営業日カレンダーは元のまま）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKDAYS = "MO,TU,WE,TH,FR"
# (理由, 名前, 色, 並び, 数えるか)。理由が None は営業日の層（ドメインの LAYER_* と同じ値）。
LAYERS = (
    (None, "営業日", "GRAPHITE", 1000, False),
    ("COMPANY", "会社の公休", "TANGERINE", 1001, True),
    ("PERSONAL", "私の休み", "SAGE", 1002, True),
    ("NATIONAL_HOLIDAY", "日本の祝日", "TOMATO", 1003, True),
)


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("calendars") as batch:
        batch.add_column(sa.Column("workdays", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("day_off_reason", sa.String(length=16), nullable=True))
        batch.add_column(
            sa.Column("counts_as_day_off", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    op.create_table(
        "calendar_days_off",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("calendar_id", _id(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("calendar_id", "day", name="uq_calendar_days_off_day"),
    )

    bind = op.get_bind()
    calendars = sa.table(
        "calendars",
        sa.column("id", _id()),
        sa.column("user_id", _id()),
        sa.column("kind", sa.String()),
        sa.column("name", sa.String()),
        sa.column("color_key", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_default", sa.Boolean()),
        sa.column("is_visible", sa.Boolean()),
        sa.column("workdays", sa.String()),
        sa.column("day_off_reason", sa.String()),
        sa.column("counts_as_day_off", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    days_off = sa.table(
        "calendar_days_off",
        sa.column("calendar_id", _id()),
        sa.column("day", sa.Date()),
        sa.column("name", sa.String()),
    )
    now = sa.func.current_timestamp()
    user_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM users ORDER BY id"))]
    for user_id in user_ids:
        first_business = bind.execute(
            sa.text(
                "SELECT id, workdays FROM business_calendars WHERE user_id = :u ORDER BY id LIMIT 1"
            ),
            {"u": user_id},
        ).first()
        workdays = first_business[1] if first_business and first_business[1] else DEFAULT_WORKDAYS
        for reason, name, color, order, counts in LAYERS:
            bind.execute(
                calendars.insert().values(
                    user_id=user_id,
                    kind="WORKWEEK" if reason is None else "DAYS_OFF",
                    name=name,
                    color_key=color,
                    sort_order=order,
                    is_default=False,
                    is_visible=True,
                    workdays=workdays if reason is None else None,
                    day_off_reason=reason,
                    counts_as_day_off=counts,
                    created_at=now,
                    updated_at=now,
                )
            )
        national_id = bind.execute(
            sa.select(calendars.c.id).where(
                calendars.c.user_id == user_id, calendars.c.day_off_reason == "NATIONAL_HOLIDAY"
            )
        ).scalar_one()
        holidays = bind.execute(
            sa.text(
                "SELECT h.holiday_date, h.name FROM business_calendar_holidays h "
                "JOIN business_calendars c ON c.id = h.calendar_id "
                "WHERE c.user_id = :u ORDER BY h.holiday_date, c.id"
            ).columns(holiday_date=sa.Date(), name=sa.String()),
            {"u": user_id},
        ).all()
        seen: set = set()
        rows = []
        for day, name in holidays:
            if day in seen:
                continue
            seen.add(day)
            rows.append({"calendar_id": national_id, "day": day, "name": name})
        if rows:
            bind.execute(days_off.insert(), rows)


def downgrade() -> None:
    op.drop_table("calendar_days_off")
    op.execute("DELETE FROM calendars WHERE kind <> 'EVENTS'")
    with op.batch_alter_table("calendars") as batch:
        batch.drop_column("counts_as_day_off")
        batch.drop_column("day_off_reason")
        batch.drop_column("workdays")
