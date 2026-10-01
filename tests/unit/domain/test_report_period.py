"""実績を見比べる期間の区切り（task #162 / ADR-0017）。"""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.exceptions import ValidationError
from src.domain.services.daily_ledger import DailyLedger
from src.domain.value_objects.report_period import (
    MAX_REPORT_PERIODS,
    ReportPeriod,
    ReportPeriodUnit,
    recent_report_periods,
    report_period_containing,
    report_periods_between,
)


def test_closing_periods_are_the_halves_of_the_month() -> None:
    assert report_periods_between(
        ReportPeriodUnit.CLOSING, date(2026, 2, 10), date(2026, 3, 1)
    ) == [
        ReportPeriod(date(2026, 2, 1), date(2026, 2, 15)),
        ReportPeriod(date(2026, 2, 16), date(2026, 2, 28)),
        ReportPeriod(date(2026, 3, 1), date(2026, 3, 15)),
    ]


def test_weeks_start_on_monday() -> None:
    # 2026-09-13 は日曜、2026-09-14 は月曜
    assert report_period_containing(ReportPeriodUnit.WEEK, date(2026, 9, 13)) == ReportPeriod(
        date(2026, 9, 7), date(2026, 9, 13)
    )
    assert report_period_containing(ReportPeriodUnit.WEEK, date(2026, 9, 14)) == ReportPeriod(
        date(2026, 9, 14), date(2026, 9, 20)
    )


def test_months_cover_the_calendar_month_across_the_year_end() -> None:
    assert report_periods_between(ReportPeriodUnit.MONTH, date(2026, 12, 31), date(2027, 1, 1)) == [
        ReportPeriod(date(2026, 12, 1), date(2026, 12, 31)),
        ReportPeriod(date(2027, 1, 1), date(2027, 1, 31)),
    ]


def test_recent_periods_end_with_the_one_containing_today() -> None:
    periods = recent_report_periods(ReportPeriodUnit.CLOSING, date(2026, 10, 1), 3)
    assert periods == [
        ReportPeriod(date(2026, 9, 1), date(2026, 9, 15)),
        ReportPeriod(date(2026, 9, 16), date(2026, 9, 30)),
        ReportPeriod(date(2026, 10, 1), date(2026, 10, 15)),
    ]


def test_a_reversed_or_too_long_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        report_periods_between(ReportPeriodUnit.WEEK, date(2026, 9, 2), date(2026, 9, 1))
    with pytest.raises(ValidationError):
        report_periods_between(
            ReportPeriodUnit.WEEK, date(2020, 1, 1), date(2020, 1, 1).replace(year=2030)
        )
    assert (
        len(report_periods_between(ReportPeriodUnit.CLOSING, date(2026, 1, 1), date(2030, 12, 31)))
        == MAX_REPORT_PERIODS
    )


def test_ledger_totals_split_task_and_off_task_time() -> None:
    ledger = DailyLedger()
    ledger.add(1, date(2026, 9, 15), 3600)
    ledger.add(None, date(2026, 9, 15), 600)
    ledger.add(1, date(2026, 9, 16), 1200)
    ledger.add(2, date(2026, 9, 16), 0)  # 0 秒は載せない
    first = ReportPeriod(date(2026, 9, 1), date(2026, 9, 15))

    assert ledger.total(first) == 4200
    assert ledger.total(first, task_only=True) == 3600
    assert ledger.total(first, task_only=False) == 600
    assert ledger.grouped(first, lambda t: "none" if t is None else f"t{t}") == {
        "t1": 3600,
        "none": 600,
    }
    assert ledger.span_by_task() == {1: (date(2026, 9, 15), date(2026, 9, 16))}
    assert list(ledger.entries()) == [
        (1, date(2026, 9, 15), 3600),
        (None, date(2026, 9, 15), 600),
        (1, date(2026, 9, 16), 1200),
    ]
