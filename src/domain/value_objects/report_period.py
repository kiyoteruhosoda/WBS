"""Period buckets for comparing actuals (task #162 / ADR-0017).

All periods are **dates in the user's time zone** (inclusive at both ends). There are 3 units:

- ``closing``: closing period (days 1–15 / day 16 to month end; same split as ``HalfMonthPeriod``)
- ``week``: 7 days starting on Monday
- ``month``: calendar month
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from src.domain.exceptions import ValidationError
from src.domain.value_objects.half_month_period import HalfMonthPeriod

MAX_REPORT_PERIODS = 120
"""Maximum number of periods listed at once (a bit over 2 years for weeks, 5 years for closings)."""


class ReportPeriodUnit(StrEnum):
    CLOSING = "closing"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, order=True)
class ReportPeriod:
    first_day: date
    last_day: date
    """Inclusive (through the end of that day)."""

    def contains(self, day: date) -> bool:
        return self.first_day <= day <= self.last_day


def report_period_containing(unit: ReportPeriodUnit, day: date) -> ReportPeriod:
    if unit is ReportPeriodUnit.CLOSING:
        half = HalfMonthPeriod.containing(day)
        return ReportPeriod(half.first_day, half.last_day)
    if unit is ReportPeriodUnit.WEEK:
        monday = day - timedelta(days=day.weekday())
        return ReportPeriod(monday, monday + timedelta(days=6))
    last = calendar.monthrange(day.year, day.month)[1]
    return ReportPeriod(day.replace(day=1), day.replace(day=last))


def report_periods_between(
    unit: ReportPeriodUnit, first_day: date, last_day: date
) -> list[ReportPeriod]:
    """Periods overlapping ``first_day``–``last_day``, oldest first (periods at the edges are included whole)."""
    if last_day < first_day:
        raise ValidationError("the end of the range must not be before its start")
    periods: list[ReportPeriod] = []
    period = report_period_containing(unit, first_day)
    while period.first_day <= last_day:
        periods.append(period)
        if len(periods) > MAX_REPORT_PERIODS:
            raise ValidationError(f"too many periods (at most {MAX_REPORT_PERIODS})")
        period = report_period_containing(unit, period.last_day + timedelta(days=1))
    return periods


def recent_report_periods(unit: ReportPeriodUnit, today: date, count: int) -> list[ReportPeriod]:
    """The latest ``count`` periods ending with the one containing ``today`` (oldest first)."""
    if count < 1:
        raise ValidationError("count must be at least 1")
    periods = [report_period_containing(unit, today)]
    while len(periods) < count:
        periods.insert(0, report_period_containing(unit, periods[0].first_day - timedelta(days=1)))
    return periods


__all__ = [
    "MAX_REPORT_PERIODS",
    "ReportPeriod",
    "ReportPeriodUnit",
    "recent_report_periods",
    "report_period_containing",
    "report_periods_between",
]
