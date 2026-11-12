"""Closing period (twice a month: days 1–15 / day 16 to month end. task #163 / ADR-0012).

A period is defined by **dates in the user's time zone**; its boundary instants are obtained
by passing a time zone to ``utc_window()`` (split at 0:00).
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
    """Inclusive (through the end of that day)."""

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
        """Refer to a period by its first day (``ValidationError`` unless it is the 1st or the 16th)."""
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
        """From 0:00 of the first day to 0:00 of the day after the last day in ``zone`` (``[start, end)``, naive UTC)."""
        return (
            local_midnight_utc(self.first_day, zone),
            local_midnight_utc(self.last_day + timedelta(days=1), zone),
        )


def local_midnight_utc(day: date, zone: tzinfo) -> datetime:
    """The instant of 0:00 on ``day`` in ``zone`` (naive UTC)."""
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC).replace(tzinfo=None)


def local_date_of(instant: datetime, zone: tzinfo) -> date:
    """Which date a naive UTC instant falls on in ``zone``."""
    return instant.replace(tzinfo=UTC).astimezone(zone).date()


def _bounds_containing(day: date) -> tuple[date, date]:
    if day.day <= FIRST_HALF_LAST_DAY:
        return day.replace(day=1), day.replace(day=FIRST_HALF_LAST_DAY)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=FIRST_HALF_LAST_DAY + 1), day.replace(day=last)


__all__ = ["HalfMonthPeriod", "local_date_of", "local_midnight_utc"]
