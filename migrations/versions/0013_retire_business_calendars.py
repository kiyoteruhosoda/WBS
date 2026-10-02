"""古い営業日カレンダーを畳み、休みの 4 層に一本化する（task #191 / ADR-0032）

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-02

- 古い営業日カレンダー（ADR-0009）の祝日のうち、まだ「日本の祝日」の層（ADR-0029）に無い日を層へ写す
  （0010 の後に古い画面で足した日を落とさないため。層がまだ無い利用者には 0010 と同じ 4 層を作る）
- 予定の繰り返しの規則の ``adjustment.calendar_id``（古いカレンダーの名指し）を外す。営業日シフトは
  休みの 4 層だけで決まる
- 表 ``business_calendar_holidays`` と ``business_calendars`` を消す

⚠ 下げると表を作り直し、休みの層がある利用者ごとに営業日カレンダーを 1 つ作る（稼働する曜日 = 営業日の層、
祝日 = 「日本の祝日」の層の日。「祝日だけ飛ばす」は切り）。外した名指しは戻らない（名指しの無い規則は
0010 の後と同じく層で寄る）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_WORKDAYS = "MO,TU,WE,TH,FR"
# 0010 と同じ層（理由, 名前, 色, 並び, 数えるか）。理由が None は営業日の層。
LAYERS = (
    (None, "営業日", "GRAPHITE", 1000, False),
    ("COMPANY", "会社の公休", "TANGERINE", 1001, True),
    ("PERSONAL", "私の休み", "SAGE", 1002, True),
    ("NATIONAL_HOLIDAY", "日本の祝日", "TOMATO", 1003, True),
)


def _id() -> sa.types.TypeEngine:
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


_calendars = sa.table(
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
_days_off = sa.table(
    "calendar_days_off",
    sa.column("calendar_id", _id()),
    sa.column("day", sa.Date()),
    sa.column("name", sa.String()),
)
_events = sa.table(
    "calendar_events",
    sa.column("id", _id()),
    sa.column("recurrence_rule", sa.Text()),
)


def _national_layer_id(bind: sa.Connection, user_id: int, workdays: str) -> int:
    """利用者の「日本の祝日」の層（無ければ 0010 と同じ 4 層を作って）。"""
    found = bind.execute(
        sa.select(_calendars.c.id).where(
            _calendars.c.user_id == user_id, _calendars.c.day_off_reason == "NATIONAL_HOLIDAY"
        )
    ).scalar()
    if found is not None:
        return found
    now = sa.func.current_timestamp()
    for reason, name, color, order, counts in LAYERS:
        bind.execute(
            _calendars.insert().values(
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
    return bind.execute(
        sa.select(_calendars.c.id).where(
            _calendars.c.user_id == user_id, _calendars.c.day_off_reason == "NATIONAL_HOLIDAY"
        )
    ).scalar_one()


def _copy_legacy_holidays(bind: sa.Connection) -> None:
    user_ids = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT DISTINCT user_id FROM business_calendars ORDER BY user_id")
        )
    ]
    for user_id in user_ids:
        first = bind.execute(
            sa.text(
                "SELECT workdays FROM business_calendars WHERE user_id = :u ORDER BY id LIMIT 1"
            ),
            {"u": user_id},
        ).scalar()
        national_id = _national_layer_id(bind, user_id, first or DEFAULT_WORKDAYS)
        have = {
            row[0]
            for row in bind.execute(
                sa.select(_days_off.c.day).where(_days_off.c.calendar_id == national_id)
            )
        }
        holidays = bind.execute(
            sa.text(
                "SELECT h.holiday_date, h.name FROM business_calendar_holidays h "
                "JOIN business_calendars c ON c.id = h.calendar_id "
                "WHERE c.user_id = :u ORDER BY h.holiday_date, c.id"
            ).columns(holiday_date=sa.Date(), name=sa.String()),
            {"u": user_id},
        ).all()
        rows = []
        for day, name in holidays:
            if day in have:
                continue
            have.add(day)
            rows.append({"calendar_id": national_id, "day": day, "name": name})
        if rows:
            bind.execute(_days_off.insert(), rows)


def _unname_adjustments(bind: sa.Connection) -> None:
    """繰り返しの規則の ``adjustment.calendar_id`` を外す（表の JSON は書き込みと同じ形で書き直す）。"""
    rows = bind.execute(
        sa.select(_events.c.id, _events.c.recurrence_rule).where(
            _events.c.recurrence_rule.is_not(None)
        )
    ).all()
    for event_id, text in rows:
        try:
            rule = json.loads(text)
        except ValueError:
            continue
        adjustment = rule.get("adjustment") if isinstance(rule, dict) else None
        if not isinstance(adjustment, dict) or "calendar_id" not in adjustment:
            continue
        del adjustment["calendar_id"]
        bind.execute(
            _events.update()
            .where(_events.c.id == event_id)
            .values(recurrence_rule=json.dumps(rule, ensure_ascii=False, sort_keys=True))
        )


def upgrade() -> None:
    bind = op.get_bind()
    _copy_legacy_holidays(bind)
    _unname_adjustments(bind)
    op.drop_table("business_calendar_holidays")
    # 索引は表と一緒に消える（MariaDB は外部キーが使う索引を先に消せない）
    op.drop_table("business_calendars")


def downgrade() -> None:
    op.create_table(
        "business_calendars",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("user_id", _id(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("workdays", sa.String(length=32), nullable=False),
        sa.Column("shift_on_holidays_only", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        "ix_business_calendars_user_id", "business_calendars", ["user_id"], unique=False
    )
    op.create_table(
        "business_calendar_holidays",
        sa.Column("id", _id(), autoincrement=True, nullable=False),
        sa.Column("calendar_id", _id(), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["calendar_id"], ["business_calendars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "calendar_id", "holiday_date", name="uq_business_calendar_holidays_date"
        ),
    )

    bind = op.get_bind()
    business = sa.table(
        "business_calendars",
        sa.column("id", _id()),
        sa.column("user_id", _id()),
        sa.column("name", sa.String()),
        sa.column("time_zone", sa.String()),
        sa.column("workdays", sa.String()),
        sa.column("shift_on_holidays_only", sa.Boolean()),
        sa.column("is_enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    holidays = sa.table(
        "business_calendar_holidays",
        sa.column("calendar_id", _id()),
        sa.column("holiday_date", sa.Date()),
        sa.column("name", sa.String()),
    )
    now = sa.func.current_timestamp()
    workweeks = bind.execute(
        sa.text(
            "SELECT c.user_id, c.workdays, u.timezone FROM calendars c "
            "JOIN users u ON u.id = c.user_id WHERE c.kind = 'WORKWEEK' ORDER BY c.user_id"
        )
    ).all()
    for user_id, workdays, time_zone in workweeks:
        bind.execute(
            business.insert().values(
                user_id=user_id,
                name="営業日",
                time_zone=time_zone or "Asia/Tokyo",
                workdays=workdays or DEFAULT_WORKDAYS,
                shift_on_holidays_only=False,
                is_enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        business_id = bind.execute(
            sa.select(sa.func.max(business.c.id)).where(business.c.user_id == user_id)
        ).scalar_one()
        days = bind.execute(
            sa.text(
                "SELECT d.day, d.name FROM calendar_days_off d JOIN calendars c ON c.id = d.calendar_id "
                "WHERE c.user_id = :u AND c.day_off_reason = 'NATIONAL_HOLIDAY' ORDER BY d.day"
            ).columns(day=sa.Date(), name=sa.String()),
            {"u": user_id},
        ).all()
        if days:
            bind.execute(
                holidays.insert(),
                [{"calendar_id": business_id, "holiday_date": d, "name": n} for d, n in days],
            )
