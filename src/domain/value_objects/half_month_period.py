"""締めの期間（月 2 回: 1〜15 日 / 16 日〜末日。task #163 / ADR-0011）。

期間は**利用者のタイムゾーンの日付**で決まる値で、区切りの瞬間はタイムゾーンを
与えて ``utc_window()`` で出す（0:00 区切り）。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from src.domain.exceptions import ValidationError

FIRST_HALF_LAST_DAY = 15


@dataclass(frozen=True, order=True)
class HalfMonthPeriod:
    first_day: date
    last_day: date
    """含む（その日の終わりまで）。"""

    def __post_init__(self) -> None:
        expected = _bounds_containing(self.first_day)
        if (self.first_day, self.last_day) != expected:
            raise ValidationError(
                f"not a closing period: {self.first_day}..{self.last_day}"
                " (periods are the 1st-15th and the 16th-end of month)"
            )

    @classmethod
    def containing(cls, day: date) -> HalfMonthPeriod:
        first, last = _bounds_containing(day)
        return cls(first, last)

    @classmethod
    def starting_on(cls, first_day: date) -> HalfMonthPeriod:
        """期間をその初日で指す（1 日か 16 日でなければ ``ValidationError``）。"""
        if first_day.day not in (1, FIRST_HALF_LAST_DAY + 1):
            raise ValidationError("a closing period starts on the 1st or the 16th")
        return cls.containing(first_day)

    def previous(self) -> HalfMonthPeriod:
        return HalfMonthPeriod.containing(self.first_day - timedelta(days=1))

    def next(self) -> HalfMonthPeriod:
        return HalfMonthPeriod.containing(self.last_day + timedelta(days=1))

    def days(self) -> list[date]:
        count = (self.last_day - self.first_day).days + 1
        return [self.first_day + timedelta(days=i) for i in range(count)]

    def utc_window(self, zone: tzinfo) -> tuple[datetime, datetime]:
        """``zone`` の初日 0:00 から末日の翌日 0:00 まで（``[始まり, 終わり)``、naive な UTC）。"""
        return (
            local_midnight_utc(self.first_day, zone),
            local_midnight_utc(self.last_day + timedelta(days=1), zone),
        )


def local_midnight_utc(day: date, zone: tzinfo) -> datetime:
    """``zone`` での ``day`` の 0:00 の瞬間（naive な UTC）。"""
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC).replace(tzinfo=None)


def local_date_of(instant: datetime, zone: tzinfo) -> date:
    """naive な UTC の瞬間が ``zone`` で何日か。"""
    return instant.replace(tzinfo=UTC).astimezone(zone).date()


def _bounds_containing(day: date) -> tuple[date, date]:
    if day.day <= FIRST_HALF_LAST_DAY:
        return day.replace(day=1), day.replace(day=FIRST_HALF_LAST_DAY)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=FIRST_HALF_LAST_DAY + 1), day.replace(day=last)


__all__ = ["HalfMonthPeriod", "local_date_of", "local_midnight_utc"]
