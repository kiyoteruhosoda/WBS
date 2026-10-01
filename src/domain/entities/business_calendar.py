"""営業日カレンダー（移植元 ``BusinessCalendar``）。

利用者ごとに持つ。繰り返しの営業日シフト（``AdjustmentRule``）が参照する。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from src.domain.exceptions import ValidationError
from src.domain.value_objects.recurrence import Weekday
from src.domain.value_objects.time_zone import TimeZoneId


@dataclass(frozen=True)
class Holiday:
    date: date
    name: str | None = None


@dataclass
class BusinessCalendar:
    id: int | None
    user_id: int
    name: str
    time_zone: TimeZoneId
    workdays: frozenset[Weekday]
    holidays: list[Holiday] = field(default_factory=list)
    shift_on_holidays_only: bool = False
    """True なら営業日シフトで飛ばすのは祝日だけ（休みの曜日にも着地してよい）。"""
    is_enabled: bool = True
    """False なら祝日の強調表示に使わない（シフトの参照は止めない。移植元と同じ）。"""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self._check_name(self.name)
        self.workdays = frozenset(self.workdays)
        # 同じ日の祝日は 1 つだけ（先に入っていた方を残す）。
        unique: dict[date, Holiday] = {}
        for holiday in self.holidays:
            unique.setdefault(holiday.date, holiday)
        self.holidays = list(unique.values())

    @staticmethod
    def _check_name(name: str) -> None:
        if not name or not name.strip():
            raise ValidationError("business calendar name must not be empty")

    def update(
        self,
        name: str,
        workdays: Iterable[Weekday],
        shift_on_holidays_only: bool,
        is_enabled: bool,
        updated_at: datetime,
    ) -> None:
        self._check_name(name)
        self.name = name
        self.workdays = frozenset(workdays)
        self.shift_on_holidays_only = shift_on_holidays_only
        self.is_enabled = is_enabled
        self.updated_at = updated_at

    def add_holiday(self, holiday: Holiday, updated_at: datetime) -> None:
        """同じ日がすでにあれば何もしない（名前も変えない）。"""
        if self.is_holiday(holiday.date):
            return
        self.holidays.append(holiday)
        self.updated_at = updated_at

    def remove_holiday(self, day: date, updated_at: datetime) -> None:
        self.holidays = [h for h in self.holidays if h.date != day]
        self.updated_at = updated_at

    def is_holiday(self, day: date) -> bool:
        return any(h.date == day for h in self.holidays)

    def is_business_day(self, day: date) -> bool:
        if self.is_holiday(day):
            return False
        return Weekday.of(day) in self.workdays

    def shift_business_days(self, base: date, amount: int) -> date:
        """``base`` から営業日を ``amount`` 日数えた日（負なら前へ）。``amount == 0`` は ``base``。"""
        if amount != 0 and not self.workdays and not self.shift_on_holidays_only:
            # 営業日が 1 日も無いカレンダーでは数え終わらない。
            raise ValidationError("business calendar has no workdays")
        current = base
        step = timedelta(days=1 if amount > 0 else -1)
        remaining = abs(amount)
        while remaining > 0:
            current = current + step
            acceptable = (
                not self.is_holiday(current)
                if self.shift_on_holidays_only
                else self.is_business_day(current)
            )
            if acceptable:
                remaining -= 1
        return current


__all__ = ["BusinessCalendar", "Holiday"]
