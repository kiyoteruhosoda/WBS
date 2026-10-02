"""休みの 4 層と営業日の判定（task #191 の 2 本目、ADR-0029）。

**営業日 = 営業日の層の曜日に当たり、かつ「休みとして数える」の印の付いた休みの日の一覧の層
（会社の公休・私の休み・日本の祝日）のどれにも無い日。** 表示のチェックには関係しない。

繰り返しの営業日シフト（ADR-0007・0009）と定常業務の回（ADR-0025）はこの判定だけを使う
（``BusinessDayShiftService`` がこれを受ける。古い営業日カレンダーは ADR-0032 で畳んだ）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.domain.entities.calendar import Calendar, CalendarKind
from src.domain.entities.day_off import DayOff
from src.domain.exceptions import ValidationError
from src.domain.value_objects.recurrence import WEEKDAYS_MON_TO_FRI, Weekday

WEEKLY_REASON = "WEEKLY"
"""曜日の休み（営業日の層の曜日に当たらない日）の理由の名前。"""


@dataclass(frozen=True)
class DayOffMark:
    """ある日が休みである理由 1 つ（画面の塗りと印、知らせの文に使う）。"""

    day: date
    reason: str
    """``DayOffReason`` の値か ``WEEKLY``（曜日の休み）。"""
    calendar_id: int | None
    name: str | None
    counts_as_day_off: bool


@dataclass
class DayOffLayers:
    workdays: frozenset[Weekday] = WEEKDAYS_MON_TO_FRI
    workweek_calendar_id: int | None = None
    layers: Sequence[Calendar] = field(default_factory=tuple)
    """休みの日の一覧の層（``DAYS_OFF``）。"""
    days_off: Sequence[DayOff] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        counted = {c.id for c in self.layers if c.counts_as_day_off}
        self._counted_days = {d.day for d in self.days_off if d.calendar_id in counted}
        self._layers_by_id = {c.id: c for c in self.layers}

    @classmethod
    def of(cls, calendars: Iterable[Calendar], days_off: Iterable[DayOff]) -> DayOffLayers:
        """利用者のカレンダー（全部でよい。層だけ拾う）と、層の日付から。"""
        calendars = list(calendars)
        workweek = next((c for c in calendars if c.kind == CalendarKind.WORKWEEK), None)
        return cls(
            workdays=workweek.workdays if workweek and workweek.workdays is not None else WEEKDAYS_MON_TO_FRI,
            workweek_calendar_id=workweek.id if workweek else None,
            layers=[c for c in calendars if c.kind == CalendarKind.DAYS_OFF],
            days_off=list(days_off),
        )

    def is_workday(self, day: date) -> bool:
        """営業日の層の曜日に当たるか（休みの日の一覧は見ない）。"""
        return Weekday.of(day) in self.workdays

    def is_counted_day_off(self, day: date) -> bool:
        """「休みとして数える」の層のどれかにある日か。"""
        return day in self._counted_days

    def is_business_day(self, day: date) -> bool:
        return self.is_workday(day) and not self.is_counted_day_off(day)

    def business_days_between(self, start: date, end: date) -> int:
        """``start``〜``end``（両端を含む）の営業日の数。逆なら 0。"""
        count = 0
        day = start
        while day <= end:
            if self.is_business_day(day):
                count += 1
            day += timedelta(days=1)
        return count

    def marks_between(self, start: date, end: date) -> list[DayOffMark]:
        """``start``〜``end`` の休みの理由（日付の順。同じ日は 曜日 → 層の並び）。数えない層の日も出す。"""
        by_day: dict[date, list[DayOffMark]] = {}
        day = start
        while day <= end:
            if not self.is_workday(day):
                by_day.setdefault(day, []).append(
                    DayOffMark(day, WEEKLY_REASON, self.workweek_calendar_id, None, True)
                )
            day += timedelta(days=1)
        order = {c.id: (c.sort_order, c.id or 0) for c in self.layers}
        for day_off in sorted(self.days_off, key=lambda d: (d.day, order.get(d.calendar_id, (0, 0)))):
            if not start <= day_off.day <= end:
                continue
            layer = self._layers_by_id.get(day_off.calendar_id)
            if layer is None or layer.day_off_reason is None:
                continue
            by_day.setdefault(day_off.day, []).append(
                DayOffMark(
                    day_off.day, layer.day_off_reason.value, layer.id, day_off.name,
                    layer.counts_as_day_off,
                )
            )
        return [mark for day in sorted(by_day) for mark in by_day[day]]

    def shift_business_days(self, base: date, amount: int) -> date:
        """``base`` から営業日を ``amount`` 日数えた日（負なら前へ）。``amount == 0`` は ``base``。"""
        if amount != 0 and not self.workdays:
            # 稼働する曜日が 1 つも無いと数え終わらない。
            raise ValidationError("the workweek layer has no workdays")
        current = base
        step = timedelta(days=1 if amount > 0 else -1)
        remaining = abs(amount)
        while remaining > 0:
            current = current + step
            if self.is_business_day(current):
                remaining -= 1
        return current


__all__ = ["WEEKLY_REASON", "DayOffLayers", "DayOffMark"]
