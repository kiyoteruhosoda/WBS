"""締めの期間の割り方（task #163）: 1〜15 日 / 16 日〜末日、月末・閏年・タイムゾーンの 0:00。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domain.exceptions import ValidationError
from src.domain.value_objects.half_month_period import HalfMonthPeriod, local_date_of


@pytest.mark.parametrize(
    ("day", "first", "last"),
    [
        (date(2026, 10, 1), date(2026, 10, 1), date(2026, 10, 15)),
        (date(2026, 10, 15), date(2026, 10, 1), date(2026, 10, 15)),
        (date(2026, 10, 16), date(2026, 10, 16), date(2026, 10, 31)),
        (date(2026, 10, 31), date(2026, 10, 16), date(2026, 10, 31)),
        (date(2026, 9, 30), date(2026, 9, 16), date(2026, 9, 30)),
        # 閏年の 2 月は 29 日まで、平年は 28 日まで
        (date(2028, 2, 29), date(2028, 2, 16), date(2028, 2, 29)),
        (date(2028, 2, 16), date(2028, 2, 16), date(2028, 2, 29)),
        (date(2027, 2, 20), date(2027, 2, 16), date(2027, 2, 28)),
        (date(2100, 2, 28), date(2100, 2, 16), date(2100, 2, 28)),  # 100 で割れて 400 で割れない
        (date(2000, 2, 17), date(2000, 2, 16), date(2000, 2, 29)),
    ],
)
def test_containing(day: date, first: date, last: date) -> None:
    period = HalfMonthPeriod.containing(day)
    assert (period.first_day, period.last_day) == (first, last)


def test_days_of_the_second_half_of_a_leap_february() -> None:
    days = HalfMonthPeriod.containing(date(2028, 2, 20)).days()
    assert len(days) == 14
    assert days[0] == date(2028, 2, 16)
    assert days[-1] == date(2028, 2, 29)


def test_previous_and_next_cross_months_and_years() -> None:
    first_half = HalfMonthPeriod.containing(date(2027, 1, 3))
    assert first_half.previous() == HalfMonthPeriod(date(2026, 12, 16), date(2026, 12, 31))
    assert first_half.previous().next() == first_half
    assert HalfMonthPeriod.containing(date(2028, 2, 16)).next() == HalfMonthPeriod(
        date(2028, 3, 1), date(2028, 3, 15)
    )


@pytest.mark.parametrize("day", [date(2026, 10, 2), date(2026, 10, 15), date(2026, 10, 31)])
def test_a_period_is_pointed_at_by_its_first_day(day: date) -> None:
    with pytest.raises(ValidationError):
        HalfMonthPeriod.starting_on(day)


def test_a_made_up_range_is_not_a_period() -> None:
    with pytest.raises(ValidationError):
        HalfMonthPeriod(date(2026, 10, 1), date(2026, 10, 31))


def test_utc_window_is_midnight_in_the_users_time_zone() -> None:
    period = HalfMonthPeriod.starting_on(date(2026, 10, 1))
    # JST の 10/1 0:00 は UTC の 9/30 15:00。終わりは 10/16 0:00 JST（含まない）
    assert period.utc_window(ZoneInfo("Asia/Tokyo")) == (
        datetime(2026, 9, 30, 15, 0),
        datetime(2026, 10, 15, 15, 0),
    )
    assert period.utc_window(ZoneInfo("UTC")) == (
        datetime(2026, 10, 1, 0, 0),
        datetime(2026, 10, 16, 0, 0),
    )


def test_utc_window_follows_daylight_saving_time() -> None:
    # 米国太平洋時間は 2026-11-01 に夏時間が終わる（-7h → -8h）
    period = HalfMonthPeriod.starting_on(date(2026, 10, 16))
    assert period.utc_window(ZoneInfo("America/Los_Angeles")) == (
        datetime(2026, 10, 16, 7, 0),
        datetime(2026, 11, 1, 7, 0),
    )
    following = period.next()
    assert following.utc_window(ZoneInfo("America/Los_Angeles"))[1] == datetime(2026, 11, 16, 8, 0)


def test_local_date_of() -> None:
    tokyo = ZoneInfo("Asia/Tokyo")
    assert local_date_of(datetime(2026, 9, 30, 14, 59), tokyo) == date(2026, 9, 30)
    assert local_date_of(datetime(2026, 9, 30, 15, 0), tokyo) == date(2026, 10, 1)
