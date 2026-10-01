"""繰り返しの振る舞いの表（移植元 CoreTests/RecurringMatrixTests.cs・MatrixTestSupport.cs）。

各試験を毎週・毎月・毎年の 3 種で回す。軸:
  操作: 作る / 直す / 消す
  範囲: この回だけ / この回以降 / すべて
  直す所: 開始日（移動）/ 終了日 / 時刻だけ / 内容だけ
  シフト: なし / 次の営業日 / 前の営業日
結果は保存した予定を展開して確かめる。

2026-06-01 と 2026-06-15 はどちらも月曜なので、6/15 を祝日にすると 3 種とも同じ
シフトの確かめ方ができる（毎週月曜・毎月 15 日・毎年 6/15）。
"""

from __future__ import annotations

import calendar as gregorian
from datetime import date, time, timedelta

import pytest

from src.application.dto.calendar_event_dto import (
    ChangeFollowingOccurrencesCommand,
    CreateRecurringEventCommand,
    OccurrenceCommand,
    SplitThisOccurrenceCommand,
    UpdateRecurringSeriesCommand,
)
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.domain.exceptions import ValidationError
from src.domain.value_objects.event_schedule import EventOccurrence, OccurrenceKey
from src.domain.value_objects.local_schedule_point import local_date_of
from src.domain.value_objects.recurrence import (
    AdjustmentRule,
    DayOfMonthMonthlyRule,
    DayOfMonthYearlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
)
from tests.unit.application.scheduling.fakes import (
    FakeClock,
    FakeTasks,
    InMemoryBusinessCalendarRepository,
    InMemoryCalendarEventRepository,
    RecordingUnitOfWork,
)
from tests.unit.domain.scheduling.support import NOW, TOKYO, utc, weekday_calendar

USER = 1
FAR_END = date(2030, 12, 31)
START_TIME = time(9, 0)
SHARED_HOLIDAY = date(2026, 6, 15)
ALL_TYPES = list(RecurrenceType)


def start_of(rule_type: RecurrenceType) -> date:
    return date(2026, 6, 1) if rule_type == RecurrenceType.WEEKLY else date(2026, 6, 15)


def rule_of(
    rule_type: RecurrenceType, end: date | None = None, adjustment: AdjustmentRule | None = None
) -> RecurrenceRule:
    end = end or FAR_END
    if rule_type == RecurrenceType.WEEKLY:
        return RecurrenceRule(rule_type, 1, end, weekly=WeeklyRule((Weekday.MONDAY,)), adjustment=adjustment)
    if rule_type == RecurrenceType.MONTHLY:
        return RecurrenceRule(rule_type, 1, end, monthly=DayOfMonthMonthlyRule(15), adjustment=adjustment)
    return RecurrenceRule(rule_type, 1, end, yearly=DayOfMonthYearlyRule(6, 15), adjustment=adjustment)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, gregorian.monthrange(year, month + 1)[1]))


def expected(rule_type: RecurrenceType, count: int) -> list[date]:
    """シフト無しの先頭 ``count`` 回の日付。"""
    start = start_of(rule_type)
    if rule_type == RecurrenceType.WEEKLY:
        return [start + timedelta(days=7 * i) for i in range(count)]
    if rule_type == RecurrenceType.MONTHLY:
        return [_add_months(start, i) for i in range(count)]
    return [start.replace(year=start.year + i) for i in range(count)]


def key(rule_type: RecurrenceType, index: int) -> OccurrenceKey:
    """回は（候補日, 系列の開始時刻）で指す。"""
    return OccurrenceKey(expected(rule_type, index + 1)[index], START_TIME)


class Matrix:
    def __init__(self) -> None:
        self.events = InMemoryCalendarEventRepository()
        self.calendars = InMemoryBusinessCalendarRepository()
        self.uc = CalendarEventUseCases(
            self.events, self.calendars, FakeTasks(), RecordingUnitOfWork(), now=FakeClock(NOW)
        )
        self.calendar_id = self.calendars.save(weekday_calendar(SHARED_HOLIDAY, calendar_id=None)).id

    def create_series(
        self, rule_type: RecurrenceType, title: str = "orig", adjustment: AdjustmentRule | None = None,
        end: date | None = None,
    ) -> int:
        start = start_of(rule_type)
        event = self.uc.create_recurring_event(
            CreateRecurringEventCommand(
                USER, title, "Asia/Tokyo", utc(start.year, start.month, start.day, 9, 0), 60,
                rule_of(rule_type, end, adjustment),
            )
        )
        assert event.id is not None
        return event.id

    def occurrences(self, event_id: int, from_date: date, to_date: date) -> list[EventOccurrence]:
        return [o for o in self.uc.list_occurrences(USER, from_date, to_date) if o.event_id == event_id]

    def dates(self, event_id: int, from_date: date, to_date: date) -> list[date]:
        return [o.date for o in self.occurrences(event_id, from_date, to_date)]

    def update_series(self, event_id: int, rule_type: RecurrenceType, **kwargs) -> None:
        start = start_of(rule_type)
        hour, minute, duration = kwargs.pop("time", (9, 0, 60))
        self.uc.update_recurring_series(
            UpdateRecurringSeriesCommand(
                event_id, USER, kwargs.pop("title", "orig"), duration,
                kwargs.pop("rule", rule_of(rule_type)),
                anchor_utc=utc(start.year, start.month, start.day, hour, minute),
                **kwargs,
            )
        )


@pytest.fixture
def m() -> Matrix:
    return Matrix()


# ── 作る ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_new_series_lands_on_the_expected_dates(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    assert m.dates(event_id, start_of(rule_type), want[-1]) == want


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_holiday_shift_none_forward_backward(m: Matrix, rule_type: RecurrenceType) -> None:
    window = (date(2026, 6, 8), date(2026, 6, 22))

    no_shift = m.create_series(rule_type, title="none")
    assert SHARED_HOLIDAY in m.dates(no_shift, *window)

    forward = m.create_series(
        rule_type, title="fwd", adjustment=AdjustmentRule.next_business_day_on_holiday(m.calendar_id)
    )
    forward_dates = m.dates(forward, *window)
    assert date(2026, 6, 16) in forward_dates
    assert SHARED_HOLIDAY not in forward_dates

    backward = m.create_series(
        rule_type, title="back", adjustment=AdjustmentRule.previous_business_day_on_holiday(m.calendar_id)
    )
    backward_dates = m.dates(backward, *window)
    assert date(2026, 6, 12) in backward_dates
    assert SHARED_HOLIDAY not in backward_dates


# ── すべての回を直す ──────────────────────────────────────────────────────


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_series_content_only_changes_titles_not_dates(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    m.update_series(event_id, rule_type, title="renamed", location="Room X")
    occurrences = m.occurrences(event_id, start_of(rule_type), want[-1])
    assert [o.date for o in occurrences] == want
    assert all(o.title == "renamed" and o.location == "Room X" for o in occurrences)


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_series_time_only_changes_every_occurrence(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    m.update_series(event_id, rule_type, time=(13, 0, 90))  # 13:00〜14:30
    occurrences = m.occurrences(event_id, start_of(rule_type), want[-1])
    assert [o.date for o in occurrences] == want
    assert all(o.start_time == time(13, 0) and o.duration_minutes == 90 for o in occurrences)


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_series_time_change_keeps_skips(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    m.uc.delete_occurrence(OccurrenceCommand(event_id, USER, key(rule_type, 1)))
    m.update_series(event_id, rule_type, time=(13, 0, 60))
    occurrences = m.occurrences(event_id, start_of(rule_type), want[-1])
    assert want[1] not in [o.date for o in occurrences]  # 鍵が付け替わって飛ばすが残る
    assert all(o.start_time.hour == 13 for o in occurrences)


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_series_shorter_end_date_reduces_occurrences(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    first_three = expected(rule_type, 3)
    m.update_series(event_id, rule_type, rule=rule_of(rule_type, end=first_three[-1]))
    assert m.dates(event_id, start_of(rule_type), expected(rule_type, 10)[-1]) == first_three


# ── この回以降を直す ──────────────────────────────────────────────────────


def _change_following(m: Matrix, event_id: int, rule_type: RecurrenceType, index: int, title: str, hour: int):
    split_key = key(rule_type, index)
    day = split_key.date
    return m.uc.change_following_occurrences(
        ChangeFollowingOccurrencesCommand(
            event_id, USER, split_key, title, utc(day.year, day.month, day.day, hour, 0), 60,
            rule_of(rule_type),
        )
    )


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_following_from_the_third_changes_only_the_rest(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 5)
    future = _change_following(m, event_id, rule_type, 2, "future", 15)

    assert len(m.events.all()) == 2
    assert m.dates(event_id, start_of(rule_type), want[-1]) == expected(rule_type, 2)
    assert future.id is not None
    future_occurrences = m.occurrences(future.id, start_of(rule_type), want[-1])
    assert [o.date for o in future_occurrences] == want[2:]
    assert all(o.title == "future" and o.start_time.hour == 15 for o in future_occurrences)


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_following_from_the_first_replaces_the_whole_series(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    whole = _change_following(m, event_id, rule_type, 0, "whole", 9)

    remaining = m.events.all()
    assert [e.id for e in remaining] == [whole.id]
    assert m.events.find_by_id(event_id) is None
    assert whole.id is not None
    assert m.dates(whole.id, start_of(rule_type), want[-1]) == want
    assert remaining[0].title == "whole"


# ── この回だけを直す ──────────────────────────────────────────────────────


def _split(m: Matrix, event_id: int, rule_type: RecurrenceType, title: str, day: date):
    return m.uc.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event_id, USER, key(rule_type, 1), title, utc(day.year, day.month, day.day, 9, 0), 60
        )
    )


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_split_this_excludes_it_and_creates_a_single(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    single = _split(m, event_id, rule_type, "special", want[1])

    series_dates = m.dates(event_id, start_of(rule_type), want[-1])
    assert want[1] not in series_dates
    assert len(series_dates) == 3
    assert len(m.events.all()) == 2
    assert single.title == "special"
    assert single.single_schedule is not None
    assert local_date_of(single.single_schedule.start_utc, TOKYO.zone) == want[1]


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_split_this_to_another_date(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    moved = want[1] + timedelta(days=2)
    single = _split(m, event_id, rule_type, "orig", moved)

    series_dates = m.dates(event_id, start_of(rule_type), want[-1] + timedelta(days=2))
    assert want[1] not in series_dates
    assert want[0] in series_dates and want[2] in series_dates
    assert single.single_schedule is not None
    assert local_date_of(single.single_schedule.start_utc, TOKYO.zone) == moved


# ── 消す ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_delete_whole_series(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    m.uc.delete_event(event_id, USER)
    assert m.events.find_by_id(event_id) is None
    assert m.events.all() == []


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_delete_this_occurrence_only(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    want = expected(rule_type, 4)
    m.uc.delete_occurrence(OccurrenceCommand(event_id, USER, key(rule_type, 1)))
    assert m.dates(event_id, start_of(rule_type), want[-1]) == [want[0], want[2], want[3]]


# ── 終了日の検査（ドメインの守り）─────────────────────────────────────────


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_create_with_end_before_start_is_rejected(m: Matrix, rule_type: RecurrenceType) -> None:
    start = start_of(rule_type)
    with pytest.raises(ValidationError):
        m.uc.create_recurring_event(
            CreateRecurringEventCommand(
                USER, "x", "Asia/Tokyo", utc(start.year, start.month, start.day, 9, 0), 60,
                rule_of(rule_type, end=start - timedelta(days=1)),
            )
        )


@pytest.mark.parametrize("rule_type", ALL_TYPES)
def test_series_update_with_end_before_start_is_rejected(m: Matrix, rule_type: RecurrenceType) -> None:
    event_id = m.create_series(rule_type)
    with pytest.raises(ValidationError):
        m.update_series(event_id, rule_type, rule=rule_of(rule_type, end=start_of(rule_type) - timedelta(days=1)))
