"""予定のカレンダー（task #191 / ADR-0027）。

利用者ごとに複数持つ（名前・色・並び順）。予定はどれか 1 つに属する。Google カレンダーと
同じく、画面に出すかどうか（``is_visible``）はカレンダーごとに持ち、サーバーに覚える
（端末をまたいで同じ）。

各利用者に **既定のカレンダー** が 1 つある（``is_default``）。移行で作り、無い利用者には
初めて使うときに作る。既定のカレンダーは消せない（消したカレンダーの予定の行き先）。

**休みの層**（task #191 の 2 本目、ADR-0029）も同じ一覧に並ぶカレンダーとして持つ（表示の選択と
組み合わせを 1 つで扱うため）。データは層ごとに分ける:

1. 営業日（``WORKWEEK``）: 稼働する曜日の規則（``workdays``）。日付の一覧ではない
2. 会社の公休（``DAYS_OFF`` / ``COMPANY``）: 日付の一覧
3. 私の休み（``DAYS_OFF`` / ``PERSONAL``）: 日付の一覧（終日）
4. 日本の祝日（``DAYS_OFF`` / ``NATIONAL_HOLIDAY``）: 日付の一覧（年ごとに入れる）

日付の一覧の層は「休みとして数える」（``counts_as_day_off``）を持つ。営業日の判定は表示の
チェックに関係なくこの印で決まる。層は利用者に 1 つずつで、消せない（予定は入れられない）。

予定のカレンダーは **仕事 / プライベート**（``scope``、ADR-0033）を持つ。仕事を土台の予定とし、
プライベートの予定は計画（実績の「予定した時間」・締めの予定の列）と打刻の既定のタスクに数えない。
プライベートのカレンダーにはタスクを結んだ予定を入れられない。既定のカレンダーは仕事のまま。

**取り込んだカレンダー**（``IMPORTED``、ADR-0037）は、外の iCalendar（.ics）を読み込んだ回を持つ
読み取り専用のカレンダー。WBS の予定は入れられず、計画・締め・打刻には数えない。表示の選択と
組み合わせは予定のカレンダーと同じ一覧で扱う。
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday

NAME_MAX_LENGTH = 200

DEFAULT_CALENDAR_NAME = "予定"
"""移行・初めて使うときに作る既定のカレンダーの名前（利用者が後から変えられる）。"""


class CalendarKind(enum.StrEnum):
    """カレンダーの種類。"""

    EVENTS = "EVENTS"
    """予定を入れるカレンダー。"""
    WORKWEEK = "WORKWEEK"
    """休みの層 1: 営業日（稼働する曜日の規則）。"""
    DAYS_OFF = "DAYS_OFF"
    """休みの層 2〜4: 休みの日の一覧（理由は ``DayOffReason``）。"""
    IMPORTED = "IMPORTED"
    """外の iCalendar を読み込んだ回を持つ、読み取り専用のカレンダー（ADR-0037）。"""


class CalendarScope(enum.StrEnum):
    """予定のカレンダーの区別（ADR-0033）。休みの層は ``WORK`` のまま（意味を持たない）。"""

    WORK = "WORK"
    """仕事。計画・打刻の既定のタスクに数える。"""
    PRIVATE = "PRIVATE"
    """プライベート。表示と通知だけ（計画に数えない・タスクを結べない）。"""


class DayOffReason(enum.StrEnum):
    """休みの日の一覧の層の理由（画面の塗りと印を分ける）。"""

    NATIONAL_HOLIDAY = "NATIONAL_HOLIDAY"
    """日本の祝日。"""
    COMPANY = "COMPANY"
    """会社の公休（年末年始など）。"""
    PERSONAL = "PERSONAL"
    """私の休み。"""


LAYER_NAMES: dict[DayOffReason | None, str] = {
    None: "営業日",
    DayOffReason.NATIONAL_HOLIDAY: "日本の祝日",
    DayOffReason.COMPANY: "会社の公休",
    DayOffReason.PERSONAL: "私の休み",
}
"""層を作るときの名前（利用者が後から変えられる）。``None`` は営業日の層。"""

LAYER_COLORS: dict[DayOffReason | None, EventColorKey] = {
    None: EventColorKey.GRAPHITE,
    DayOffReason.NATIONAL_HOLIDAY: EventColorKey.TOMATO,
    DayOffReason.COMPANY: EventColorKey.TANGERINE,
    DayOffReason.PERSONAL: EventColorKey.SAGE,
}

LAYER_SORT_BASE = 1000
"""層の並び順の始まり（予定のカレンダーの後ろに並べる）。"""

LAYER_ORDER: tuple[DayOffReason | None, ...] = (
    None, DayOffReason.COMPANY, DayOffReason.PERSONAL, DayOffReason.NATIONAL_HOLIDAY,
)


def calendar_name(raw: str) -> str:
    """前後の空白を落とした名前。空・長すぎるものは断る。"""
    name = raw.strip()
    if not name:
        raise ValidationError("a calendar needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a calendar name must be at most {NAME_MAX_LENGTH} characters")
    return name


@dataclass
class Calendar:
    id: int | None
    user_id: int
    name: str
    color_key: EventColorKey = EventColorKey.DEFAULT
    """``DEFAULT`` は色の指定なし（予定は結んだタスクのカテゴリの色・標準の予定色で描く）。"""
    sort_order: int = 0
    is_default: bool = False
    is_visible: bool = True
    """カレンダーの画面に出すか。⚠ 出すかどうかだけで、分類・打刻の既定のタスク・「今日」・締めは
    これに関係なく全部のカレンダーを見る。"""
    kind: CalendarKind = CalendarKind.EVENTS
    workdays: frozenset[Weekday] | None = None
    """営業日の層の稼働する曜日（ほかの種類は ``None``）。"""
    day_off_reason: DayOffReason | None = None
    """休みの日の一覧の層の理由（ほかの種類は ``None``）。"""
    counts_as_day_off: bool = False
    """休みの日の一覧の層: 営業日の判定で休みとして数えるか。"""
    scope: CalendarScope = CalendarScope.WORK
    """予定のカレンダーの区別（仕事 / プライベート。ADR-0033）。"""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = calendar_name(self.name)
        if self.kind == CalendarKind.WORKWEEK:
            self.workdays = frozenset(self.workdays if self.workdays is not None else WEEKDAYS_MON_TO_FRI)
        if self.kind == CalendarKind.DAYS_OFF and self.day_off_reason is None:
            raise ValidationError("a days-off calendar needs a reason")
        if self.scope == CalendarScope.PRIVATE and (not self.holds_events or self.is_default):
            raise ValidationError("only a non-default events calendar can be private")

    @property
    def holds_events(self) -> bool:
        """予定を入れられるか（休みの層には入れない）。"""
        return self.kind == CalendarKind.EVENTS

    @property
    def is_day_off_layer(self) -> bool:
        return self.kind in (CalendarKind.WORKWEEK, CalendarKind.DAYS_OFF)

    @property
    def is_imported(self) -> bool:
        """外の iCalendar を読み込んだカレンダーか（読み取り専用。ADR-0037）。"""
        return self.kind == CalendarKind.IMPORTED

    @property
    def is_private(self) -> bool:
        """プライベートの予定のカレンダーか（計画に数えない・タスクを結べない。ADR-0033）。"""
        return self.scope == CalendarScope.PRIVATE

    def change_scope(self, scope: CalendarScope, updated_at: datetime) -> None:
        """仕事 / プライベートを変える。休みの層と既定のカレンダーはプライベートにできない。"""
        if scope == self.scope:
            return
        if scope == CalendarScope.PRIVATE and (not self.holds_events or self.is_default):
            raise ValidationError("only a non-default events calendar can be private")
        self.scope = scope
        self.updated_at = updated_at

    @classmethod
    def create_layer(
        cls, user_id: int, reason: DayOffReason | None, created_at: datetime,
        workdays: Iterable[Weekday] | None = None,
    ) -> Calendar:
        """休みの層。``reason`` が ``None`` なら営業日の層。日付の一覧は最初から休みとして数える。"""
        return cls(
            id=None, user_id=user_id, name=LAYER_NAMES[reason], color_key=LAYER_COLORS[reason],
            sort_order=LAYER_SORT_BASE + LAYER_ORDER.index(reason), is_visible=True,
            kind=CalendarKind.WORKWEEK if reason is None else CalendarKind.DAYS_OFF,
            workdays=frozenset(workdays) if workdays is not None else None,
            day_off_reason=reason, counts_as_day_off=reason is not None,
            created_at=created_at, updated_at=created_at,
        )

    def change_layer(
        self, *, counts_as_day_off: bool | None, workdays: Iterable[Weekday] | None, updated_at: datetime
    ) -> None:
        """休みの層の設定（数えるか・稼働する曜日）。``None`` は今のまま。"""
        if counts_as_day_off is not None and self.kind == CalendarKind.DAYS_OFF:
            self.counts_as_day_off = counts_as_day_off
        if workdays is not None:
            if self.kind != CalendarKind.WORKWEEK:
                raise ValidationError("only the workweek layer has workdays")
            self.workdays = frozenset(workdays)
        self.updated_at = updated_at

    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        name: str,
        color_key: EventColorKey,
        sort_order: int,
        created_at: datetime,
        is_default: bool = False,
        scope: CalendarScope = CalendarScope.WORK,
    ) -> Calendar:
        """新しいカレンダー。最初から表示する（毎回選び直させない）。"""
        return cls(
            id=None, user_id=user_id, name=name, color_key=color_key, sort_order=sort_order,
            is_default=is_default, is_visible=True, scope=scope,
            created_at=created_at, updated_at=created_at,
        )

    @classmethod
    def create_imported(
        cls, *, user_id: int, name: str, color_key: EventColorKey, sort_order: int, created_at: datetime
    ) -> Calendar:
        """取り込んだカレンダー（ADR-0037）。最初から表示する。"""
        return cls(
            id=None, user_id=user_id, name=name, color_key=color_key, sort_order=sort_order,
            is_visible=True, kind=CalendarKind.IMPORTED, created_at=created_at, updated_at=created_at,
        )

    @classmethod
    def create_default(cls, user_id: int, created_at: datetime) -> Calendar:
        return cls.create(
            user_id=user_id, name=DEFAULT_CALENDAR_NAME, color_key=EventColorKey.DEFAULT,
            sort_order=0, created_at=created_at, is_default=True,
        )

    def change(self, *, name: str, color_key: EventColorKey, updated_at: datetime) -> None:
        self.name = calendar_name(name)
        self.color_key = color_key
        self.updated_at = updated_at

    def show(self, visible: bool, updated_at: datetime) -> None:
        if self.is_visible == visible:
            return
        self.is_visible = visible
        self.updated_at = updated_at

    def place_at(self, sort_order: int, updated_at: datetime) -> None:
        if self.sort_order == sort_order:
            return
        self.sort_order = sort_order
        self.updated_at = updated_at


__all__ = [
    "DEFAULT_CALENDAR_NAME",
    "LAYER_COLORS",
    "LAYER_NAMES",
    "LAYER_ORDER",
    "LAYER_SORT_BASE",
    "DayOffReason",
    "NAME_MAX_LENGTH",
    "Calendar",
    "CalendarKind",
    "CalendarScope",
    "calendar_name",
]
