"""予定の集約（移植元 CoreTests/CalendarEventTests.cs・CalendarEventSpanTests.cs）。"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest

from src.domain.entities.calendar_event import (
    CalendarEvent,
    EventKind,
    ExceptionType,
)
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import (
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.recurrence import RecurrenceType, Weekday
from tests.unit.domain.scheduling.support import (
    NOW,
    TOKYO,
    UTC_ZONE,
    recurring_event,
    single_event,
    utc,
    weekly_monday_from_0420,
    weekly_rule,
)

KEY_0427 = OccurrenceKey(date(2026, 4, 27), time(10, 0))


def test_create_single_sets_properties() -> None:
    event = single_event(utc(2026, 4, 20, 10, 0), title="テスト会議", location="会議室A")
    assert event.is_single() and not event.is_recurring()
    assert event.title == "テスト会議"
    assert event.location == "会議室A"
    assert event.version == 1
    assert event.created_at == event.updated_at == NOW


def test_create_recurring_weekly_sets_properties() -> None:
    event = weekly_monday_from_0420()
    assert event.is_recurring()
    assert event.recurring_schedule is not None
    assert event.recurring_schedule.recurrence_rule.rule_type == RecurrenceType.WEEKLY


def test_recurring_cross_day_is_allowed() -> None:
    # 23:00 から 2 時間は翌 1:00 まで。長さだけで表す（time-model §11）。
    schedule = RecurringEventSchedule(utc(2026, 4, 20, 23, 0), 120, weekly_rule(Weekday.MONDAY))
    assert schedule.duration_minutes == 120


def test_title_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        single_event(utc(2026, 4, 20, 10, 0), title="  ")


def test_kind_and_schedule_must_agree() -> None:
    with pytest.raises(ValidationError):
        CalendarEvent(
            id=None, user_id=1, kind=EventKind.RECURRING, title="x", time_zone=TOKYO,
            single_schedule=SingleEventSchedule(utc(2026, 4, 20, 10, 0), 60),
        )


def test_recurring_anchor_after_end_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CalendarEvent.create_recurring(
            user_id=1, title="x", time_zone=TOKYO,
            schedule=RecurringEventSchedule(
                utc(2026, 4, 20, 10, 0), 60, weekly_rule(Weekday.MONDAY, end=date(2026, 4, 19))
            ),
            created_at=NOW,
        )


def test_anchor_on_end_date_is_allowed_in_the_event_time_zone() -> None:
    # 2026-04-20 08:00 JST は UTC では 04-19 23:00。判定は予定のタイムゾーンのローカル日で行う。
    event = recurring_event(utc(2026, 4, 20, 8, 0), weekly_rule(Weekday.MONDAY, end=date(2026, 4, 20)))
    assert event.series_start_date() == date(2026, 4, 20)


def test_skip_occurrence_adds_exception() -> None:
    event = weekly_monday_from_0420()
    event.skip_occurrence(KEY_0427, NOW)
    assert event.has_exception_for(KEY_0427)
    assert len(event.exceptions) == 1
    assert event.exceptions[0].type == ExceptionType.SKIP


def test_skip_occurrence_twice_is_still_one_skip() -> None:
    event = weekly_monday_from_0420()
    event.skip_occurrence(KEY_0427, NOW)
    event.skip_occurrence(KEY_0427, NOW)
    assert len(event.exceptions) == 1
    assert event.exceptions[0].type == ExceptionType.SKIP


def test_change_recurrence_end_date() -> None:
    event = weekly_monday_from_0420()
    event.change_recurrence_end_date(date(2026, 6, 30), NOW)
    assert event.recurring_schedule is not None
    assert event.recurring_schedule.recurrence_rule.end_date == date(2026, 6, 30)


def test_change_details_updates_title_and_version() -> None:
    event = weekly_monday_from_0420()
    event.change_details(
        title="新タイトル", location=None, description="メモ", task_id=7, updated_at=datetime(2026, 5, 2)
    )
    assert event.title == "新タイトル"
    assert event.description == "メモ"
    assert event.task_id == 7
    assert event.version == 2
    assert event.updated_at == datetime(2026, 5, 2)


def test_change_details_increases_version_by_one_each_time() -> None:
    event = weekly_monday_from_0420()
    for title in ("更新1", "更新2"):
        event.change_details(title=title, location=None, description=None, task_id=None, updated_at=NOW)
    assert event.version == 3


def test_set_color_without_change_does_not_bump_version() -> None:
    event = single_event(utc(2026, 4, 20, 10, 0), color_key=EventColorKey.BASIL)
    event.set_color(EventColorKey.BASIL, NOW)
    assert event.version == 1
    event.set_color(EventColorKey.TOMATO, NOW)
    assert (event.color_key, event.version) == (EventColorKey.TOMATO, 2)


def test_single_event_cannot_skip() -> None:
    event = single_event(utc(2026, 4, 20, 10, 0))
    with pytest.raises(ValidationError):
        event.skip_occurrence(OccurrenceKey(date(2026, 4, 20), time(10, 0)), NOW)


def test_recurring_event_cannot_be_rescheduled_as_single() -> None:
    with pytest.raises(ValidationError):
        weekly_monday_from_0420().reschedule_single(SingleEventSchedule(utc(2026, 4, 21), 60), NOW)


def test_remove_occurrence_exception() -> None:
    event = weekly_monday_from_0420()
    event.skip_occurrence(KEY_0427, NOW)
    event.remove_occurrence_exception(KEY_0427, NOW)
    assert not event.has_exception_for(KEY_0427)


def test_remove_occurrence_exception_not_found() -> None:
    with pytest.raises(NotFoundError):
        weekly_monday_from_0420().remove_occurrence_exception(KEY_0427, NOW)


def test_move_occurrence_replaces_previous_move_of_the_same_occurrence() -> None:
    event = weekly_monday_from_0420()
    for new_date in (date(2026, 4, 28), date(2026, 4, 29)):
        event.move_occurrence(
            KEY_0427, new_date=new_date, new_start_time=time(14, 0), duration_minutes=60,
            title=None, location=None, updated_at=NOW,
        )
    assert [m.new_date for m in event.moves] == [date(2026, 4, 29)]


def test_remove_occurrence_move_not_found() -> None:
    with pytest.raises(NotFoundError):
        weekly_monday_from_0420().remove_occurrence_move(KEY_0427, NOW)


def test_changing_series_start_time_rekeys_skips_and_moves() -> None:
    event = weekly_monday_from_0420()
    event.skip_occurrence(KEY_0427, NOW)
    other = OccurrenceKey(date(2026, 5, 4), time(10, 0))
    event.move_occurrence(
        other, new_date=date(2026, 5, 5), new_start_time=time(15, 0), duration_minutes=60,
        title=None, location=None, updated_at=NOW,
    )
    assert event.recurring_schedule is not None
    rule = event.recurring_schedule.recurrence_rule

    event.change_recurrence_schedule(RecurringEventSchedule(utc(2026, 4, 20, 13, 0), 60, rule), NOW)

    assert event.exceptions[0].occurrence_key == OccurrenceKey(date(2026, 4, 27), time(13, 0))
    assert event.moves[0].occurrence_key == OccurrenceKey(date(2026, 5, 4), time(13, 0))


def test_ensure_version() -> None:
    event = weekly_monday_from_0420()
    event.ensure_version(None)
    event.ensure_version(1)
    with pytest.raises(ConflictError):
        event.ensure_version(2)


# ── 期間の粗い絞り込み（CalendarEventSpanTests）───────────────────────────


def test_single_span_is_the_event_day() -> None:
    event = single_event(datetime(2026, 5, 20, 9, 0), tz=UTC_ZONE)
    assert event.active_date_span() == (date(2026, 5, 20), date(2026, 5, 20))


def test_single_span_ending_at_midnight_does_not_reach_the_next_day() -> None:
    event = single_event(utc(2026, 5, 1, 0, 0), 1440)
    assert event.active_date_span() == (date(2026, 5, 1), date(2026, 5, 1))


def test_single_span_crossing_midnight_reaches_the_next_day() -> None:
    event = single_event(utc(2026, 4, 25, 23, 0), 180)
    assert event.active_date_span() == (date(2026, 4, 25), date(2026, 4, 26))


def test_recurring_span_is_start_to_end_date() -> None:
    event = recurring_event(
        datetime(2026, 1, 5, 10, 0), weekly_rule(Weekday.MONDAY, end=date(2027, 12, 31)), 30, tz=UTC_ZONE
    )
    assert event.active_date_span() == (date(2026, 1, 5), date(2027, 12, 31))


def test_recurring_span_widens_to_moved_occurrences() -> None:
    event = weekly_monday_from_0420()
    event.move_occurrence(
        OccurrenceKey(date(2026, 12, 28), time(10, 0)), new_date=date(2027, 1, 4),
        new_start_time=time(10, 0), duration_minutes=60, title=None, location=None, updated_at=NOW,
    )
    assert event.active_date_span() == (date(2026, 4, 20), date(2027, 1, 4))


def test_overlaps_period_hits_inside_and_misses_far_outside() -> None:
    event = recurring_event(
        datetime(2026, 1, 5, 10, 0), weekly_rule(Weekday.MONDAY, end=date(2026, 3, 31)), 30, tz=UTC_ZONE
    )
    assert event.overlaps_period(date(2026, 2, 1), date(2026, 2, 28))
    # 31 日の余白より外は当たらない
    assert not event.overlaps_period(date(2026, 6, 1), date(2026, 6, 30))
    assert not event.overlaps_period(date(2025, 1, 1), date(2025, 1, 31))


def test_indexed_day_span_adds_the_margin() -> None:
    event = single_event(datetime(2026, 5, 20, 9, 0), tz=UTC_ZONE)
    start, end = event.indexed_day_span()
    assert start == date(2026, 5, 20).toordinal() - 31
    assert end == date(2026, 5, 20).toordinal() + 31
