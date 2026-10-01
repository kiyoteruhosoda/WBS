"""予定のユースケース（移植元 CoreTests/CalendarEventApplicationServiceTests.cs ＋ WBS で足した分）。

移植元は画面の「開始〜終了・終日」で受けていたが、こちらは UTC の瞬間 ＋ 長さで受ける。
試験の中では Asia/Tokyo の壁時計を ``utc(...)`` で瞬間に直して渡す。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from src.application.dto.calendar_event_dto import (
    ChangeFollowingOccurrencesCommand,
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    MoveOccurrenceCommand,
    OccurrenceCommand,
    RescheduleSingleEventCommand,
    SplitThisOccurrenceCommand,
    UpdateEventCommand,
    UpdateRecurringSeriesCommand,
)
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.domain.entities.calendar_event import CalendarEvent, ExceptionType
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.local_schedule_point import local_date_of, local_time_of
from src.domain.value_objects.recurrence import (
    NO_END_DATE,
    WEEKDAYS_MON_TO_FRI,
    AdjustmentRule,
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
from tests.unit.domain.scheduling.support import TOKYO, utc, weekday_calendar, weekly_rule

USER = 1
OTHER_USER = 2
CLOCK_START = datetime(2026, 5, 1, 0, 0)
WEEKDAYS = tuple(sorted(WEEKDAYS_MON_TO_FRI, key=lambda w: w.iso_index))


class World:
    def __init__(self) -> None:
        self.events = InMemoryCalendarEventRepository()
        self.calendars = InMemoryBusinessCalendarRepository()
        self.tasks = FakeTasks({10: USER, 20: OTHER_USER})
        self.uow = RecordingUnitOfWork()
        self.clock = FakeClock(CLOCK_START)
        self.uc = CalendarEventUseCases(
            self.events, self.calendars, self.tasks, self.uow, now=self.clock
        )

    def single(self, title: str = "sample", **kwargs) -> CalendarEvent:
        """5/20 9:00〜10:00 の単発（移植元 ``CreateAndSaveSingleEvent``）。"""
        return self.uc.create_single_event(
            CreateSingleEventCommand(
                user_id=kwargs.pop("user_id", USER), title=title, time_zone="Asia/Tokyo",
                start_utc=utc(2026, 5, 20, 9, 0), duration_minutes=60, **kwargs,
            )
        )

    def weekly_wednesday(self, **kwargs) -> CalendarEvent:
        """5/1 9:30 から毎週水曜・60 分、12/31 まで（移植元 ``SaveRecurringEvent``）。"""
        return self.uc.create_recurring_event(
            CreateRecurringEventCommand(
                user_id=kwargs.pop("user_id", USER), title="rec", time_zone="Asia/Tokyo",
                anchor_utc=utc(2026, 5, 1, 9, 30), duration_minutes=60,
                recurrence_rule=weekly_rule(Weekday.WEDNESDAY), **kwargs,
            )
        )

    def daily_from_0629(self) -> CalendarEvent:
        return self.uc.create_recurring_event(
            CreateRecurringEventCommand(
                user_id=USER, title="Daily", time_zone="Asia/Tokyo",
                anchor_utc=utc(2026, 6, 29, 9, 0), duration_minutes=60,
                recurrence_rule=RecurrenceRule(
                    RecurrenceType.WEEKLY, 1, NO_END_DATE, weekly=WeeklyRule(WEEKDAYS)
                ),
            )
        )

    def get(self, event_id: int | None) -> CalendarEvent:
        assert event_id is not None
        return self.uc.get_event(event_id, USER)


@pytest.fixture
def w() -> World:
    return World()


def _local(instant: datetime) -> tuple[date, time]:
    return local_date_of(instant, TOKYO.zone), local_time_of(instant, TOKYO.zone)


KEY_0506 = OccurrenceKey(date(2026, 5, 6), time(9, 30))


# ── 作る ────────────────────────────────────────────────────────────────


def test_create_single_event_is_saved(w: World) -> None:
    event = w.single("Meeting", location="Room A")
    assert len(w.events.all()) == 1
    assert (event.title, event.location, event.is_single()) == ("Meeting", "Room A", True)
    assert w.uow.commits == 1


def test_all_day_single_is_midnight_plus_one_day(w: World) -> None:
    event = w.uc.create_single_event(
        CreateSingleEventCommand(USER, "Holiday", "Asia/Tokyo", utc(2026, 5, 20), 24 * 60)
    )
    assert event.single_schedule is not None
    assert _local(event.single_schedule.start_utc) == (date(2026, 5, 20), time(0, 0))
    assert event.single_schedule.duration_minutes == 1440


def test_created_and_updated_at_come_from_the_clock(w: World) -> None:
    event = w.single()
    assert event.created_at == event.updated_at == CLOCK_START


def test_update_moves_updated_at_to_the_advanced_clock(w: World) -> None:
    event = w.single()
    w.clock.current = CLOCK_START + timedelta(hours=3)
    w.uc.update_event(UpdateEventCommand(event.id, USER, "Touched"))
    saved = w.get(event.id)
    assert saved.updated_at == CLOCK_START + timedelta(hours=3)
    assert saved.created_at == CLOCK_START


def test_create_recurring_event_is_saved(w: World) -> None:
    event = w.weekly_wednesday()
    assert event.is_recurring()
    assert event.title == "rec"


def test_create_rejects_unknown_time_zone(w: World) -> None:
    with pytest.raises(ValidationError):
        w.uc.create_single_event(CreateSingleEventCommand(USER, "x", "Mars/Base", utc(2026, 5, 1), 60))


# ── 直す ────────────────────────────────────────────────────────────────


def test_update_title_and_location(w: World) -> None:
    event = w.single()
    w.uc.update_event(UpdateEventCommand(event.id, USER, "Updated", location="Room B"))
    saved = w.get(event.id)
    assert (saved.title, saved.location) == ("Updated", "Room B")


def test_update_single_can_change_date_and_time(w: World) -> None:
    event = w.single()
    w.uc.update_event(
        UpdateEventCommand(
            event.id, USER, "x", start_utc=utc(2026, 6, 1, 14, 0), duration_minutes=60
        )
    )
    saved = w.get(event.id)
    assert saved.single_schedule is not None
    assert _local(saved.single_schedule.start_utc) == (date(2026, 6, 1), time(14, 0))
    assert saved.single_schedule.duration_minutes == 60


def test_update_without_color_keeps_the_existing_color(w: World) -> None:
    event = w.single(color_key=EventColorKey.BASIL)
    w.uc.update_event(
        UpdateEventCommand(
            event.id, USER, "sample", start_utc=utc(2026, 5, 21, 10, 0), duration_minutes=60
        )
    )
    saved = w.get(event.id)
    assert saved.color_key == EventColorKey.BASIL
    assert saved.single_schedule is not None
    assert _local(saved.single_schedule.start_utc)[0] == date(2026, 5, 21)


def test_reschedule_single_changes_only_the_time(w: World) -> None:
    event = w.single(color_key=EventColorKey.BASIL, description="drag memo", task_id=10)
    w.uc.reschedule_single_event(
        RescheduleSingleEventCommand(event.id, USER, utc(2026, 5, 22, 13, 0), 90)
    )
    saved = w.get(event.id)
    assert (saved.title, saved.description, saved.color_key, saved.task_id) == (
        "sample", "drag memo", EventColorKey.BASIL, 10,
    )
    assert saved.single_schedule is not None
    assert _local(saved.single_schedule.start_utc) == (date(2026, 5, 22), time(13, 0))
    assert saved.single_schedule.duration_minutes == 90


def test_reschedule_rejects_recurring(w: World) -> None:
    event = w.weekly_wednesday()
    with pytest.raises(ValidationError):
        w.uc.reschedule_single_event(
            RescheduleSingleEventCommand(event.id, USER, utc(2026, 5, 22, 13, 0), 90)
        )


def test_update_recurring_series_changes_rule_time_and_details(w: World) -> None:
    event = w.weekly_wednesday()
    new_rule = RecurrenceRule(
        RecurrenceType.WEEKLY, 2, date(2026, 12, 31),
        weekly=WeeklyRule((Weekday.MONDAY, Weekday.FRIDAY)),
    )
    w.uc.update_recurring_series(
        UpdateRecurringSeriesCommand(
            event.id, USER, "Renamed", 60, new_rule, location="Room B",
            anchor_utc=utc(2026, 5, 1, 13, 0),
        )
    )
    saved = w.get(event.id)
    assert (saved.title, saved.location) == ("Renamed", "Room B")
    assert saved.recurring_schedule is not None
    rule = saved.recurring_schedule.recurrence_rule
    assert rule.weekly is not None
    assert set(rule.weekly.weekdays) == {Weekday.MONDAY, Weekday.FRIDAY}
    assert rule.interval == 2
    # 先頭の回の日付は 5/1 のまま、時刻だけ 13:00
    assert _local(saved.recurring_schedule.anchor_utc) == (date(2026, 5, 1), time(13, 0))


def test_update_recurring_series_without_anchor_keeps_the_anchor(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.update_recurring_series(
        UpdateRecurringSeriesCommand(event.id, USER, "x", 30, weekly_rule(Weekday.WEDNESDAY))
    )
    saved = w.get(event.id)
    assert saved.recurring_schedule is not None
    assert saved.recurring_schedule.anchor_utc == utc(2026, 5, 1, 9, 30)
    assert saved.recurring_schedule.duration_minutes == 30


def test_update_recurring_series_with_new_start_date_moves_the_anchor(w: World) -> None:
    # 月〜金の系列（6/29 月から）を 6/30 の回から「すべて」で開いて保存 → アンカーが 6/30 へ。
    event = w.daily_from_0629()
    assert event.recurring_schedule is not None
    w.uc.update_recurring_series(
        UpdateRecurringSeriesCommand(
            event.id, USER, "Daily", 60, event.recurring_schedule.recurrence_rule,
            anchor_utc=utc(2026, 6, 30, 9, 0),
        )
    )
    saved = w.get(event.id)
    assert saved.recurring_schedule is not None
    assert _local(saved.recurring_schedule.anchor_utc)[0] == date(2026, 6, 30)


def test_update_recurring_series_rejects_single(w: World) -> None:
    event = w.single()
    with pytest.raises(ValidationError):
        w.uc.update_recurring_series(
            UpdateRecurringSeriesCommand(event.id, USER, "x", 60, weekly_rule(Weekday.MONDAY))
        )


# ── 飛ばす・この回だけ ────────────────────────────────────────────────────


def test_skip_occurrence(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.skip_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))
    saved = w.get(event.id)
    assert len(saved.exceptions) == 1
    assert saved.exceptions[0].type == ExceptionType.SKIP
    assert saved.exceptions[0].occurrence_key == KEY_0506


def test_delete_occurrence_is_the_same_as_skip(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.delete_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))
    assert w.get(event.id).exceptions[0].type == ExceptionType.SKIP


def test_restore_occurrence_undoes_a_skip(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.skip_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))
    w.uc.restore_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))
    assert w.get(event.id).exceptions == []
    with pytest.raises(NotFoundError):
        w.uc.restore_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))


def test_split_this_occurrence_skips_it_and_creates_a_single(w: World) -> None:
    event = w.weekly_wednesday(task_id=10)
    single = w.uc.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event.id, USER, KEY_0506, "Special", utc(2026, 5, 6, 10, 0), 60, location="Lab"
        )
    )
    assert len(w.events.all()) == 2
    series = w.get(event.id)
    assert [(e.type, e.occurrence_key) for e in series.exceptions] == [(ExceptionType.SKIP, KEY_0506)]
    assert single.is_single()
    assert (single.title, single.location, single.task_id) == ("Special", "Lab", 10)
    assert single.time_zone == series.time_zone
    assert single.single_schedule is not None
    assert _local(single.single_schedule.start_utc) == (date(2026, 5, 6), time(10, 0))
    assert w.uow.commits == 2  # 作成 1 ＋ 切り出し 1（切り出しは 2 件を 1 度に確定）


def test_split_this_occurrence_to_another_date(w: World) -> None:
    event = w.weekly_wednesday()
    single = w.uc.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event.id, USER, KEY_0506, "Moved Meeting", utc(2026, 5, 8, 11, 0), 60
        )
    )
    assert single.single_schedule is not None
    assert _local(single.single_schedule.start_utc) == (date(2026, 5, 8), time(11, 0))


def test_split_this_occurrence_rejects_single(w: World) -> None:
    event = w.single()
    with pytest.raises(ValidationError):
        w.uc.split_this_occurrence(
            SplitThisOccurrenceCommand(
                event.id, USER, OccurrenceKey(date(2026, 5, 20), time(9, 0)), "X",
                utc(2026, 5, 20, 9, 0), 60,
            )
        )
    assert len(w.events.all()) == 1  # 単発は作られていない


def test_move_occurrence_and_cancel_the_move(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.move_occurrence(
        MoveOccurrenceCommand(event.id, USER, KEY_0506, utc(2026, 5, 7, 15, 0), 45, title="振替")
    )
    moved = w.get(event.id).moves
    assert [(m.new_date, m.new_start_time, m.new_duration_minutes, m.title) for m in moved] == [
        (date(2026, 5, 7), time(15, 0), 45, "振替")
    ]
    occurrences = w.uc.list_occurrences(USER, date(2026, 5, 4), date(2026, 5, 10))
    assert [(o.date, o.is_moved, o.title) for o in occurrences] == [(date(2026, 5, 7), True, "振替")]

    w.uc.cancel_move_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))
    assert w.get(event.id).moves == []
    with pytest.raises(NotFoundError):
        w.uc.cancel_move_occurrence(OccurrenceCommand(event.id, USER, KEY_0506))


# ── この回以降 ────────────────────────────────────────────────────────────


def _following(w: World, event_id: int | None, key: OccurrenceKey, **kwargs):
    return w.uc.change_following_occurrences(
        ChangeFollowingOccurrencesCommand(
            event_id=event_id,
            user_id=USER,
            from_occurrence_key=key,
            title=kwargs.pop("title", "New Series"),
            anchor_utc=kwargs.pop("anchor_utc", utc(key.date.year, key.date.month, key.date.day, 10, 0)),
            duration_minutes=60,
            recurrence_rule=kwargs.pop("rule", weekly_rule(Weekday.WEDNESDAY)),
            **kwargs,
        )
    )


def test_change_following_ends_the_original_the_day_before(w: World) -> None:
    event = w.weekly_wednesday(task_id=10)
    new_series = _following(w, event.id, KEY_0506)
    assert len(w.events.all()) == 2
    original = w.get(event.id)
    assert original.recurring_schedule is not None
    assert original.recurring_schedule.recurrence_rule.end_date == date(2026, 5, 5)
    assert new_series.title == "New Series"
    assert new_series.task_id == 10  # 元の系列のタスクを引き継ぐ
    assert new_series.recurring_schedule is not None
    assert _local(new_series.recurring_schedule.anchor_utc)[0] == date(2026, 5, 6)


def test_change_following_keeps_the_end_date_the_user_chose(w: World) -> None:
    event = w.weekly_wednesday()
    new_series = _following(w, event.id, KEY_0506, rule=weekly_rule(Weekday.WEDNESDAY, end=date(2026, 8, 31)))
    assert new_series.recurring_schedule is not None
    assert new_series.recurring_schedule.recurrence_rule.end_date == date(2026, 8, 31)


def test_change_following_with_end_on_the_split_day(w: World) -> None:
    event = w.weekly_wednesday()
    new_series = _following(w, event.id, KEY_0506, rule=weekly_rule(Weekday.WEDNESDAY, end=date(2026, 5, 6)))
    original = w.get(event.id)
    assert original.recurring_schedule is not None
    assert original.recurring_schedule.recurrence_rule.end_date == date(2026, 5, 5)
    assert new_series.recurring_schedule is not None
    assert new_series.recurring_schedule.recurrence_rule.end_date == date(2026, 5, 6)
    assert _local(new_series.recurring_schedule.anchor_utc)[0] == date(2026, 5, 6)


def test_change_following_with_a_new_start_date(w: World) -> None:
    # 月〜金（6/29 から）の 6/30 の回を「以降」で開き、開始を 7/1 へ動かす。
    event = w.daily_from_0629()
    key = OccurrenceKey(date(2026, 6, 30), time(9, 0))
    new_series = _following(
        w, event.id, key, title="Daily", anchor_utc=utc(2026, 7, 1, 9, 0),
        rule=RecurrenceRule(RecurrenceType.WEEKLY, 1, NO_END_DATE, weekly=WeeklyRule(WEEKDAYS)),
    )
    original = w.get(event.id)
    assert original.recurring_schedule is not None
    assert original.recurring_schedule.recurrence_rule.end_date == date(2026, 6, 29)
    assert new_series.recurring_schedule is not None
    assert _local(new_series.recurring_schedule.anchor_utc)[0] == date(2026, 7, 1)


# ── 消す ────────────────────────────────────────────────────────────────


def test_delete_following_ends_the_series_the_day_before(w: World) -> None:
    event = w.weekly_wednesday()
    w.uc.delete_following_occurrences(OccurrenceCommand(event.id, USER, KEY_0506))
    remaining = w.events.all()
    assert [e.id for e in remaining] == [event.id]
    assert remaining[0].recurring_schedule is not None
    assert remaining[0].recurring_schedule.recurrence_rule.end_date == date(2026, 5, 5)


def test_delete_following_from_the_first_occurrence_deletes_the_series(w: World) -> None:
    event = w.weekly_wednesday()
    first = OccurrenceKey(date(2026, 5, 1), time(9, 30))
    w.uc.delete_following_occurrences(OccurrenceCommand(event.id, USER, first))
    assert w.events.all() == []


def test_delete_event(w: World) -> None:
    event = w.single()
    w.uc.delete_event(event.id, USER)
    assert w.events.all() == []


# ── WBS で足した決まり: 持ち主・楽観ロック・タスク・営業日カレンダー ──────────


def test_other_users_event_is_not_found(w: World) -> None:
    event = w.single()
    assert event.id is not None
    with pytest.raises(NotFoundError):
        w.uc.get_event(event.id, OTHER_USER)
    with pytest.raises(NotFoundError):
        w.uc.update_event(UpdateEventCommand(event.id, OTHER_USER, "hijack"))
    with pytest.raises(NotFoundError):
        w.uc.delete_event(event.id, OTHER_USER)
    assert w.get(event.id).title == "sample"


def test_period_lookup_only_returns_own_events(w: World) -> None:
    w.single()
    w.single("other", user_id=OTHER_USER)
    found = w.uc.find_by_period(USER, date(2026, 5, 1), date(2026, 5, 31))
    assert [e.title for e in found] == ["sample"]
    occurrences = w.uc.list_occurrences(OTHER_USER, date(2026, 5, 1), date(2026, 5, 31))
    assert [o.title for o in occurrences] == ["other"]


def test_stale_version_is_a_conflict_and_changes_nothing(w: World) -> None:
    event = w.single()
    w.uc.update_event(UpdateEventCommand(event.id, USER, "first", expected_version=1))
    with pytest.raises(ConflictError):
        w.uc.update_event(UpdateEventCommand(event.id, USER, "second", expected_version=1))
    saved = w.get(event.id)
    assert saved.title == "first"
    assert saved.version == 2


def test_task_must_belong_to_the_user(w: World) -> None:
    assert w.single(task_id=10).task_id == 10
    with pytest.raises(NotFoundError):
        w.single(task_id=20)  # 他人のタスク
    with pytest.raises(NotFoundError):
        w.single(task_id=99)  # 無いタスク


def test_split_can_unlink_the_task(w: World) -> None:
    event = w.weekly_wednesday(task_id=10)
    single = w.uc.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event.id, USER, KEY_0506, "x", utc(2026, 5, 6, 9, 30), 60, task_id=None
        )
    )
    assert single.task_id is None


def test_adjustment_calendar_must_belong_to_the_user(w: World) -> None:
    others = w.calendars.save(weekday_calendar(calendar_id=None, user_id=OTHER_USER))
    with pytest.raises(NotFoundError):
        w.uc.create_recurring_event(
            CreateRecurringEventCommand(
                USER, "x", "Asia/Tokyo", utc(2026, 5, 1, 9, 0), 60,
                weekly_rule(Weekday.MONDAY, adjustment=AdjustmentRule.next_business_day_on_holiday(others.id)),
            )
        )


def test_list_occurrences_applies_the_referenced_business_calendar(w: World) -> None:
    calendar = w.calendars.save(weekday_calendar(date(2026, 5, 4), calendar_id=None))
    w.uc.create_recurring_event(
        CreateRecurringEventCommand(
            USER, "月曜", "Asia/Tokyo", utc(2026, 5, 1, 9, 0), 60,
            weekly_rule(Weekday.MONDAY, adjustment=AdjustmentRule.next_business_day_on_holiday(calendar.id)),
        )
    )
    dates = [o.date for o in w.uc.list_occurrences(USER, date(2026, 5, 1), date(2026, 5, 12))]
    assert dates == [date(2026, 5, 5), date(2026, 5, 11)]


def test_list_occurrences_in_the_viewer_time_zone(w: World) -> None:
    # 6/15 10:00 JST は New York では 6/14 21:00（EDT）。閲覧者の 6/14 に入る。
    w.uc.create_single_event(
        CreateSingleEventCommand(USER, "JST", "Asia/Tokyo", utc(2026, 6, 15, 10, 0), 60)
    )
    in_new_york = w.uc.list_occurrences(USER, date(2026, 6, 14), date(2026, 6, 14), "America/New_York")
    assert [(o.date, o.start_time) for o in in_new_york] == [(date(2026, 6, 14), time(21, 0))]
    assert in_new_york[0].series_key == OccurrenceKey(date(2026, 6, 15), time(10, 0))
    assert w.uc.list_occurrences(USER, date(2026, 6, 15), date(2026, 6, 15), "America/New_York") == []


def test_period_must_not_be_reversed(w: World) -> None:
    with pytest.raises(ValidationError):
        w.uc.list_occurrences(USER, date(2026, 6, 2), date(2026, 6, 1))
