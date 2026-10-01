"""実績を見比べる期間の区切り（task #162 / ADR-0017）。

期間はすべて**利用者のタイムゾーンの日付**（両端を含む）。単位は 3 つ:

- ``closing``: 締めの期間（1〜15 日 / 16 日〜末日。``HalfMonthPeriod`` と同じ区切り）
- ``week``: 月曜始まりの 7 日
- ``month``: 暦の月
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from src.domain.exceptions import ValidationError
from src.domain.value_objects.half_month_period import HalfMonthPeriod

MAX_REPORT_PERIODS = 120
"""1 回に並べる期間の上限（週なら 2 年強・締めなら 5 年）。"""


class ReportPeriodUnit(StrEnum):
    CLOSING = "closing"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True, order=True)
class ReportPeriod:
    first_day: date
    last_day: date
    """含む（その日の終わりまで）。"""

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
    """``first_day``〜``last_day`` に掛かる期間を古い順に（端の期間は丸ごと含める）。"""
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
    """``today`` を含む期間で終わる、直近の ``count`` 期間（古い順）。"""
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
