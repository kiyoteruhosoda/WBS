"""値オブジェクト（移植元 CoreTests/ValueObjectTests.cs）。

移植元の ``LocalDateValue`` / ``LocalTimeValue`` は Python の ``date`` / ``time`` に置き換えたので、
その足し算・比較の試験は写さない（標準ライブラリの振る舞い）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from src.domain.exceptions import ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import (
    EventOccurrence,
    OccurrenceKey,
    SingleEventSchedule,
)
from src.domain.value_objects.recurrence import (
    DayOfMonthMonthlyRule,
    DayOfMonthYearlyRule,
    NthWeekdayMonthlyRule,
    NthWeekdayYearlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
)
from src.domain.value_objects.time_zone import TimeZoneId

END = date(2026, 12, 31)


def test_occurrence_key_equality() -> None:
    k1 = OccurrenceKey(date(2026, 4, 20), time(10, 0))
    k2 = OccurrenceKey(date(2026, 4, 20), time(10, 0))
    assert k1 == k2
    assert hash(k1) == hash(k2)


def test_occurrence_key_different_date_not_equal() -> None:
    assert OccurrenceKey(date(2026, 4, 20), time(10, 0)) != OccurrenceKey(date(2026, 4, 21), time(10, 0))


@pytest.mark.parametrize("rule_type", list(RecurrenceType))
def test_recurrence_rule_requires_the_matching_sub_rule(rule_type: RecurrenceType) -> None:
    with pytest.raises(ValidationError):
        RecurrenceRule(rule_type, 1, END)


def test_recurrence_rule_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RecurrenceRule(RecurrenceType.WEEKLY, 0, END, weekly=WeeklyRule((Weekday.MONDAY,)))


def test_recurrence_rule_with_end_date_keeps_everything_else() -> None:
    rule = RecurrenceRule(RecurrenceType.WEEKLY, 2, END, weekly=WeeklyRule((Weekday.FRIDAY,)))
    changed = rule.with_end_date(date(2026, 6, 30))
    assert changed.end_date == date(2026, 6, 30)
    assert (changed.rule_type, changed.interval, changed.weekly) == (rule.rule_type, 2, rule.weekly)


def test_weekly_rule_needs_a_weekday_and_is_normalized() -> None:
    with pytest.raises(ValidationError):
        WeeklyRule(())
    rule = WeeklyRule((Weekday.SUNDAY, Weekday.WEDNESDAY, Weekday.SUNDAY))
    assert rule.weekdays == (Weekday.WEDNESDAY, Weekday.SUNDAY)


@pytest.mark.parametrize("week_index", [0, -2, 6])
def test_nth_weekday_rejects_invalid_week_index(week_index: int) -> None:
    # time-model §11: 1〜5 か -1（最終）。0 は不可。
    with pytest.raises(ValidationError):
        NthWeekdayMonthlyRule(week_index, Weekday.MONDAY)
    with pytest.raises(ValidationError):
        NthWeekdayYearlyRule(4, week_index, Weekday.MONDAY)


def test_day_and_month_ranges_are_checked() -> None:
    with pytest.raises(ValidationError):
        DayOfMonthMonthlyRule(32)
    with pytest.raises(ValidationError):
        DayOfMonthYearlyRule(13, 1)
    with pytest.raises(ValidationError):
        DayOfMonthYearlyRule(4, 0)


def test_weekday_of_known_date() -> None:
    assert Weekday.of(date(2026, 4, 20)) == Weekday.MONDAY
    assert Weekday.of(date(2026, 5, 3)) == Weekday.SUNDAY
    assert Weekday.SUNDAY.iso_index == 6


def test_time_zone_invalid_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TimeZoneId("Invalid/Zone")
    with pytest.raises(ValidationError):
        TimeZoneId("")


def test_time_zone_equality_is_by_name() -> None:
    assert TimeZoneId("Asia/Tokyo") == TimeZoneId("Asia/Tokyo")
    assert TimeZoneId("Asia/Tokyo") != TimeZoneId("UTC")


def test_single_schedule_rejects_non_positive_duration() -> None:
    with pytest.raises(ValidationError):
        SingleEventSchedule(datetime(2026, 4, 20, 3, 0), 0)


def test_single_schedule_normalizes_aware_start_to_naive_utc() -> None:
    jst = timezone(timedelta(hours=9))
    schedule = SingleEventSchedule(datetime(2026, 4, 21, 14, 0, tzinfo=jst), 90)
    assert schedule.start_utc == datetime(2026, 4, 21, 5, 0)
    assert schedule.end_utc == datetime(2026, 4, 21, 6, 30)


def test_color_key_has_the_same_eleven_keys_as_the_desktop_app() -> None:
    # 移植元の EventColorKey と同じ 11 個（DEFAULT ＝ 色の指定なし を含む）。
    assert len(EventColorKey) == 11
    assert EventColorKey.DEFAULT in EventColorKey


def test_occurrence_minute_arithmetic() -> None:
    occurrence = EventOccurrence(None, date(2026, 4, 25), time(23, 0), 180, "深夜")
    assert occurrence.start_minute_of_day == 23 * 60
    assert occurrence.end_minute_from_start_day == 26 * 60
    assert occurrence.crosses_midnight
    assert not occurrence.is_all_day
    assert EventOccurrence(None, date(2026, 5, 1), time(0, 0), 1440, "終日").is_all_day
