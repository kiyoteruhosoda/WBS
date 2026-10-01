"""営業日カレンダー（移植元 CoreTests/BusinessCalendarTests.cs）。"""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.exceptions import ValidationError
from tests.unit.domain.scheduling.support import NOW, TOKYO, weekday_calendar

NEW_YEAR = date(2026, 1, 1)


def _default() -> BusinessCalendar:
    return weekday_calendar(NEW_YEAR)


def test_weekday_without_holiday_is_business_day() -> None:
    assert _default().is_business_day(date(2026, 4, 20))  # 月


def test_weekend_is_not_business_day() -> None:
    assert not _default().is_business_day(date(2026, 4, 18))  # 土


def test_holiday_is_not_business_day() -> None:
    assert not _default().is_business_day(NEW_YEAR)  # 木だが祝日


def test_shift_forward_skips_weekend() -> None:
    assert _default().shift_business_days(date(2026, 4, 17), 1) == date(2026, 4, 20)


def test_shift_backward() -> None:
    assert _default().shift_business_days(date(2026, 4, 20), -1) == date(2026, 4, 17)


def test_shift_on_holidays_only_does_not_skip_weekend() -> None:
    calendar = weekday_calendar(NEW_YEAR, shift_on_holidays_only=True)
    assert calendar.shift_business_days(date(2026, 4, 17), 1) == date(2026, 4, 18)


def test_shift_on_holidays_only_skips_holiday() -> None:
    calendar = weekday_calendar(NEW_YEAR, shift_on_holidays_only=True)
    assert calendar.shift_business_days(date(2025, 12, 31), 1) == date(2026, 1, 2)


def test_shift_on_holidays_only_default_is_false() -> None:
    assert not _default().shift_on_holidays_only


def test_update_sets_shift_on_holidays_only() -> None:
    calendar = _default()
    calendar.update(calendar.name, calendar.workdays, True, True, NOW)
    assert calendar.shift_on_holidays_only
    assert calendar.holidays == [Holiday(NEW_YEAR, "祝")]  # 祝日は残る


def test_add_holiday_ignores_duplicate_date() -> None:
    calendar = _default()
    calendar.add_holiday(Holiday(NEW_YEAR, "別名"), NOW)
    assert calendar.holidays == [Holiday(NEW_YEAR, "祝")]


def test_remove_holiday() -> None:
    calendar = _default()
    calendar.remove_holiday(NEW_YEAR, NOW)
    assert not calendar.is_holiday(NEW_YEAR)


def test_shift_zero_returns_the_same_day() -> None:
    assert _default().shift_business_days(date(2026, 4, 18), 0) == date(2026, 4, 18)


def test_calendar_without_workdays_cannot_count_business_days() -> None:
    calendar = BusinessCalendar(None, 1, "空", TOKYO, frozenset())
    with pytest.raises(ValidationError):
        calendar.shift_business_days(date(2026, 4, 20), 1)


def test_name_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        BusinessCalendar(None, 1, " ", TOKYO, frozenset())
