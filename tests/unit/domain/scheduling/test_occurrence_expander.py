"""回の展開（移植元 CoreTests/OccurrenceExpanderTests.cs）。

移植元の各試験を 1 本ずつ写した。予定はすべて Asia/Tokyo。
"""

from __future__ import annotations

from datetime import date, time

from src.domain.entities.calendar_event import (
    EventException,
    EventMove,
    ExceptionOverride,
)
from src.domain.services.occurrence_expander import OccurrenceExpander
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.recurrence import (
    AdjustmentAction,
    AdjustmentCondition,
    AdjustmentRule,
    AdjustmentShiftUnit,
    DayOfMonthMonthlyRule,
    DayOfMonthYearlyRule,
    LastDayOfMonthMonthlyRule,
    MonthlyRule,
    NthWeekdayMonthlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
)
from tests.unit.domain.scheduling.support import (
    recurring_event,
    single_event,
    utc,
    weekday_calendar,
    weekly_monday_from_0420,
    weekly_rule,
)

expander = OccurrenceExpander()
KEY_0427 = OccurrenceKey(date(2026, 4, 27), time(10, 0))
APRIL = (date(2026, 4, 20), date(2026, 4, 30))


def test_single_in_range_returns_one() -> None:
    event = single_event(utc(2026, 4, 20, 10, 0), title="テスト")
    results = expander.expand(event, date(2026, 4, 1), date(2026, 4, 30))
    assert len(results) == 1
    assert results[0].title == "テスト"
    assert results[0].start_time == time(10, 0)
    assert results[0].series_key is None


def test_single_out_of_range_returns_empty() -> None:
    event = single_event(utc(2026, 5, 20, 10, 0))
    assert expander.expand(event, date(2026, 4, 1), date(2026, 4, 30)) == []


def test_weekly_generates_correct_count() -> None:
    # 2026 年 4 月の月曜は 6・13・20・27。開始は 20 日なので 20 と 27。
    results = expander.expand(weekly_monday_from_0420(), *APRIL)
    assert [r.date for r in results] == [date(2026, 4, 20), date(2026, 4, 27)]
    assert all(r.series_key == OccurrenceKey(r.date, time(10, 0)) for r in results)


def test_weekly_with_skip_excludes_skipped() -> None:
    event = weekly_monday_from_0420(exceptions=[EventException.skip(KEY_0427)])
    results = expander.expand(event, *APRIL)
    assert [r.date for r in results] == [date(2026, 4, 20)]


def test_weekly_with_override_returns_overridden_values() -> None:
    # 古いデータの「上書き」例外は読めること。
    override = EventException.override_with(KEY_0427, ExceptionOverride(title="変更済み"))
    results = expander.expand(weekly_monday_from_0420(exceptions=[override]), *APRIL)
    overridden = next(r for r in results if r.date == date(2026, 4, 27))
    assert overridden.title == "変更済み"
    assert overridden.is_overridden
    assert overridden.location == "会議室A"  # 上書きしていない項目は系列のまま


def test_weekly_with_move_shows_moved_date() -> None:
    move = EventMove(KEY_0427, date(2026, 4, 28), time(14, 0), 60)
    results = expander.expand(weekly_monday_from_0420(moves=[move]), *APRIL)
    assert len(results) == 2
    moved = next(r for r in results if r.is_moved)
    assert moved.date == date(2026, 4, 28)
    assert moved.start_time.hour == 14


def test_weekly_overridden_then_moved_keeps_override_content_at_moved_date() -> None:
    override = EventException.override_with(KEY_0427, ExceptionOverride(title="変更済み"))
    move = EventMove(KEY_0427, date(2026, 4, 28), time(14, 0), 60)
    results = expander.expand(weekly_monday_from_0420(exceptions=[override], moves=[move]), *APRIL)
    moved = next(r for r in results if r.is_moved)
    assert (moved.date, moved.start_time.hour, moved.title) == (date(2026, 4, 28), 14, "変更済み")


def test_monthly_nth_weekday() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 6, 30),
        monthly=NthWeekdayMonthlyRule(2, Weekday.MONDAY),
    )
    event = recurring_event(utc(2026, 4, 1, 10, 0), rule, title="月例")
    results = expander.expand(event, date(2026, 4, 1), date(2026, 6, 30))
    # 第 2 月曜: 4/13・5/11・6/8
    assert [r.date for r in results] == [date(2026, 4, 13), date(2026, 5, 11), date(2026, 6, 8)]


def test_business_day_adjustment_shifts_holiday() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 5, 31),
        monthly=DayOfMonthMonthlyRule(4),
        adjustment=AdjustmentRule.previous_business_day_on_holiday(1),
    )
    event = recurring_event(utc(2026, 5, 1, 10, 0), rule, title="調整テスト")
    calendar = weekday_calendar(date(2026, 5, 4), date(2026, 5, 3))
    results = expander.expand(event, date(2026, 5, 1), date(2026, 5, 31), calendar)
    # 5/4 祝日 → 5/3 祝日・5/2 土 → 5/1（金）
    assert [r.date for r in results] == [date(2026, 5, 1)]


def test_cancel_on_holiday_drops_only_the_holiday_occurrence() -> None:
    rule = weekly_rule(
        Weekday.MONDAY, end=date(2026, 5, 31),
        adjustment=AdjustmentRule(
            AdjustmentCondition.HOLIDAY, AdjustmentShiftUnit.BUSINESS_DAY, 0, 1,
            AdjustmentAction.CANCEL,
        ),
    )
    event = recurring_event(utc(2026, 5, 1, 10, 0), rule, title="祝日はキャンセル")
    results = expander.expand(
        event, date(2026, 5, 1), date(2026, 5, 31), weekday_calendar(date(2026, 5, 4))
    )
    assert [r.date for r in results] == [date(2026, 5, 11), date(2026, 5, 18), date(2026, 5, 25)]


def _monthly_minus_business_days(monthly: MonthlyRule, days_before: int):
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 6, 30),
        monthly=monthly,
        adjustment=AdjustmentRule(
            AdjustmentCondition.ALWAYS, AdjustmentShiftUnit.BUSINESS_DAY, -days_before, 1
        ),
    )
    return recurring_event(utc(2026, 6, 1, 13, 0), rule, title="3営業日前13時")


def test_three_business_days_before_the_15th_at_13() -> None:
    # 2026-06-15 は月曜。3 営業日前は 6/10（水）13:00。
    event = _monthly_minus_business_days(DayOfMonthMonthlyRule(15), 3)
    results = expander.expand(event, date(2026, 6, 1), date(2026, 6, 30), weekday_calendar())
    assert [(r.date, r.start_time) for r in results] == [(date(2026, 6, 10), time(13, 0))]


def test_three_business_days_before_month_end_at_13() -> None:
    # 2026-06-30 は火曜。3 営業日前は 6/25（木）13:00。
    event = _monthly_minus_business_days(LastDayOfMonthMonthlyRule(), 3)
    results = expander.expand(event, date(2026, 6, 1), date(2026, 6, 30), weekday_calendar())
    assert [(r.date, r.start_time) for r in results] == [(date(2026, 6, 25), time(13, 0))]


def test_business_days_before_skip_holidays_when_counting() -> None:
    # 6/11（木）が祝日なら 6/15 から 3 営業日前は 12・10・9 → 6/9。
    event = _monthly_minus_business_days(DayOfMonthMonthlyRule(15), 3)
    results = expander.expand(
        event, date(2026, 6, 1), date(2026, 6, 30), weekday_calendar(date(2026, 6, 11))
    )
    assert [r.date for r in results] == [date(2026, 6, 9)]


def test_shift_from_outside_the_window_lands_inside() -> None:
    # 窓は 6/22〜6/26。月末（6/30）は窓の外だが、3 営業日前の 6/25 は窓の中なので出す。
    event = _monthly_minus_business_days(LastDayOfMonthMonthlyRule(), 3)
    results = expander.expand(event, date(2026, 6, 22), date(2026, 6, 26), weekday_calendar())
    assert [r.date for r in results] == [date(2026, 6, 25)]
    assert results[0].series_key == OccurrenceKey(date(2026, 6, 30), time(13, 0))


def test_yearly_generates_correct_dates() -> None:
    rule = RecurrenceRule(
        RecurrenceType.YEARLY, 1, date(2028, 12, 31), yearly=DayOfMonthYearlyRule(4, 20)
    )
    event = recurring_event(utc(2026, 4, 20, 9, 0), rule, title="年次レビュー")
    results = expander.expand(event, date(2026, 1, 1), date(2028, 12, 31))
    assert [r.date for r in results] == [date(2026, 4, 20), date(2027, 4, 20), date(2028, 4, 20)]
    assert all(r.start_time == time(9, 0) for r in results)


def test_recurring_all_day_is_midnight_plus_1440() -> None:
    rule = weekly_rule(Weekday.MONDAY, end=date(2026, 4, 30))
    event = recurring_event(utc(2026, 4, 20, 0, 0), rule, 24 * 60, title="終日イベント")
    results = expander.expand(event, *APRIL)
    assert [r.date for r in results] == [date(2026, 4, 20), date(2026, 4, 27)]
    assert all(r.is_all_day and r.start_time == time(0, 0) for r in results)


def test_weekly_after_end_date_returns_empty() -> None:
    rule = weekly_rule(Weekday.MONDAY, end=date(2026, 4, 26))
    event = recurring_event(utc(2026, 4, 20, 10, 0), rule, title="期限切れ会議")
    assert expander.expand(event, date(2026, 4, 27), date(2026, 5, 31)) == []


def test_adjustment_does_not_shift_a_non_holiday() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 5, 31),
        monthly=DayOfMonthMonthlyRule(1),
        adjustment=AdjustmentRule.previous_business_day_on_holiday(1),
    )
    event = recurring_event(utc(2026, 5, 1, 10, 0), rule, title="非祝日テスト")
    results = expander.expand(
        event, date(2026, 5, 1), date(2026, 5, 31), weekday_calendar(date(2026, 5, 4))
    )
    assert [r.date for r in results] == [date(2026, 5, 1)]


def test_adjustment_without_calendar_leaves_dates_alone() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 5, 31),
        monthly=DayOfMonthMonthlyRule(4),
        adjustment=AdjustmentRule.previous_business_day_on_holiday(1),
    )
    event = recurring_event(utc(2026, 5, 1, 10, 0), rule)
    assert [r.date for r in expander.expand(event, date(2026, 5, 1), date(2026, 5, 31))] == [
        date(2026, 5, 4)
    ]


def test_occurrence_moved_into_the_window_from_outside_is_expanded() -> None:
    move = EventMove(KEY_0427, date(2026, 5, 13), time(14, 0), 60)
    results = expander.expand(
        weekly_monday_from_0420(moves=[move]), date(2026, 5, 10), date(2026, 5, 16)
    )
    moved = next(r for r in results if r.is_moved)
    assert moved.date == date(2026, 5, 13)
    assert moved.series_key == KEY_0427
    assert [r.date for r in results] == [date(2026, 5, 11), date(2026, 5, 13)]


def test_weekly_sunday_past_end_does_not_cut_off_other_weekdays() -> None:
    # 日・水、終了 5/7（木）。5/4 の週の日曜（5/10）は終了の後だが、水曜 5/6 は出す。
    rule = weekly_rule(Weekday.SUNDAY, Weekday.WEDNESDAY, end=date(2026, 5, 7))
    event = recurring_event(utc(2026, 5, 1, 10, 0), rule, title="日水テスト")
    dates = [r.date for r in expander.expand(event, date(2026, 5, 1), date(2026, 5, 7))]
    assert dates == [date(2026, 5, 3), date(2026, 5, 6)]


def test_weekly_interval_two() -> None:
    rule = weekly_rule(Weekday.MONDAY, Weekday.FRIDAY, interval=2)
    event = recurring_event(utc(2026, 4, 20, 10, 0), rule)
    dates = [r.date for r in expander.expand(event, date(2026, 4, 20), date(2026, 5, 17))]
    # 4/20 の週 → 5/4 の週（4/27 の週は飛ばす）
    assert dates == [date(2026, 4, 20), date(2026, 4, 24), date(2026, 5, 4), date(2026, 5, 8)]


def test_monthly_day_31_skips_short_months() -> None:
    rule = RecurrenceRule(RecurrenceType.MONTHLY, 1, date(2026, 6, 30), monthly=DayOfMonthMonthlyRule(31))
    event = recurring_event(utc(2026, 1, 31, 10, 0), rule)
    dates = [r.date for r in expander.expand(event, date(2026, 1, 1), date(2026, 6, 30))]
    assert dates == [date(2026, 1, 31), date(2026, 3, 31), date(2026, 5, 31)]


def test_monthly_last_weekday_of_month() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(2026, 6, 30), monthly=NthWeekdayMonthlyRule(-1, Weekday.FRIDAY)
    )
    event = recurring_event(utc(2026, 4, 1, 10, 0), rule)
    dates = [r.date for r in expander.expand(event, date(2026, 4, 1), date(2026, 6, 30))]
    assert dates == [date(2026, 4, 24), date(2026, 5, 29), date(2026, 6, 26)]


# ── 暦の上限（9999-12-31 は「終了日なし」）────────────────────────────────


def test_weekly_up_to_year_9999_does_not_overflow() -> None:
    rule = weekly_rule(Weekday.MONDAY, end=date(9999, 12, 31))
    event = recurring_event(utc(9999, 12, 1, 10, 0), rule)
    results = expander.expand(event, date(9999, 12, 1), date(9999, 12, 31))
    # 9999 年 12 月の月曜は 6・13・20・27（12/31 は金曜）
    assert len(results) == 4
    assert results[-1].date == date(9999, 12, 27)


def test_monthly_up_to_year_9999_does_not_overflow() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(9999, 12, 31), monthly=DayOfMonthMonthlyRule(15)
    )
    event = recurring_event(utc(9999, 10, 1, 10, 0), rule)
    results = expander.expand(event, date(9999, 10, 1), date(9999, 12, 31))
    assert len(results) == 3
    assert results[-1].date == date(9999, 12, 15)


def test_yearly_up_to_year_9999_does_not_overflow() -> None:
    rule = RecurrenceRule(
        RecurrenceType.YEARLY, 1, date(9999, 12, 31), yearly=DayOfMonthYearlyRule(12, 31)
    )
    event = recurring_event(utc(9997, 1, 1, 10, 0), rule)
    results = expander.expand(event, date(9997, 1, 1), date(9999, 12, 31))
    assert len(results) == 3
    assert results[-1].date == date(9999, 12, 31)


def test_adjusted_series_near_year_9999_does_not_overflow() -> None:
    rule = RecurrenceRule(
        RecurrenceType.MONTHLY, 1, date(9999, 12, 31), monthly=DayOfMonthMonthlyRule(15),
        adjustment=AdjustmentRule.next_business_day_on_holiday(1),
    )
    event = recurring_event(utc(9999, 12, 1, 10, 0), rule)
    results = expander.expand(event, date(9999, 12, 1), date(9999, 12, 31), weekday_calendar())
    assert [r.date for r in results] == [date(9999, 12, 15)]
