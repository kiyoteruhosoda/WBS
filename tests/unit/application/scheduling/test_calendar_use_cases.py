"""予定のカレンダー・表示の選択・表示の組み合わせ（task #191、ADR-0027）。

- 一覧で既定のカレンダーが無ければ作る（1 つだけ）
- 新しいカレンダーは末尾・最初から表示
- 他人のカレンダー・組み合わせには触れない（404）
- 消すと中の予定は既定へ移る。既定は消せない
- 表示の選択は全部を置き換える。組み合わせを当てると入っているものだけが表示
- 予定は既定のカレンダーへ入り、編集で移せる。回にはカレンダーの色が付く
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.application.dto.calendar_event_dto import (
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    SplitThisOccurrenceCommand,
    UpdateEventCommand,
)
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.application.use_cases.calendar_use_cases import CalendarUseCases
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.recurrence import Weekday
from tests.unit.application.scheduling.fakes import (
    FakeClock,
    FakeTasks,
    InMemoryBusinessCalendarRepository,
    InMemoryCalendarEventRepository,
    InMemoryCalendarRepository,
    InMemoryCalendarViewPresetRepository,
    RecordingUnitOfWork,
)
from tests.unit.domain.scheduling.support import utc, weekly_rule

USER = 1
OTHER_USER = 2


def _events_only(calendars):
    """予定のカレンダーだけ（休みの 4 層は一覧の後ろに並ぶ。ADR-0029）。"""
    return [c for c in calendars if c.holds_events]


class World:
    def __init__(self) -> None:
        self.events = InMemoryCalendarEventRepository()
        self.calendar_repo = InMemoryCalendarRepository()
        self.presets = InMemoryCalendarViewPresetRepository()
        self.uow = RecordingUnitOfWork()
        self.clock = FakeClock(datetime(2026, 10, 1, 0, 0))
        self.calendars = CalendarUseCases(
            self.calendar_repo, self.presets, self.events, self.uow, now=self.clock
        )
        self.uc = CalendarEventUseCases(
            self.events, InMemoryBusinessCalendarRepository(), FakeTasks({}), self.uow,
            now=self.clock, event_calendars=self.calendar_repo,
        )

    def default_id(self, user_id: int = USER) -> int:
        found = [c for c in self.calendars.list_calendars(user_id) if c.is_default]
        assert len(found) == 1
        assert found[0].id is not None
        return found[0].id

    def single(self, user_id: int = USER, **kwargs):
        return self.uc.create_single_event(
            CreateSingleEventCommand(
                user_id=user_id, title="会議", time_zone="Asia/Tokyo",
                start_utc=utc(2026, 10, 5, 9, 0), duration_minutes=60, **kwargs,
            )
        )


@pytest.fixture
def w() -> World:
    return World()


# ── カレンダー ──────────────────────────────────────────────────────────


def test_listing_creates_one_default_calendar_once(w: World) -> None:
    first = w.calendars.list_calendars(USER)
    again = w.calendars.list_calendars(USER)
    assert [(c.name, c.is_default, c.is_visible) for c in _events_only(first)] == [("予定", True, True)]
    assert [c.id for c in again] == [c.id for c in first]


def test_new_calendar_goes_last_and_starts_visible(w: World) -> None:
    w.calendars.list_calendars(USER)
    created = w.calendars.create_calendar(USER, " 仕事 ", EventColorKey.TOMATO)
    listed = _events_only(w.calendars.list_calendars(USER))
    assert [c.name for c in listed] == ["予定", "仕事"]
    assert (created.is_visible, created.is_default, created.color_key) == (
        True, False, EventColorKey.TOMATO,
    )


def test_blank_name_is_refused(w: World) -> None:
    with pytest.raises(ValidationError):
        w.calendars.create_calendar(USER, "   ", EventColorKey.DEFAULT)


def test_other_users_calendar_cannot_be_touched(w: World) -> None:
    theirs = w.calendars.create_calendar(OTHER_USER, "他人", EventColorKey.BASIL)
    assert theirs.id is not None
    with pytest.raises(NotFoundError):
        w.calendars.update_calendar(theirs.id, USER, "奪う", EventColorKey.TOMATO)
    with pytest.raises(NotFoundError):
        w.calendars.delete_calendar(theirs.id, USER)
    with pytest.raises(NotFoundError):
        w.calendars.set_visible_calendars(USER, [theirs.id])
    with pytest.raises(NotFoundError):
        w.calendars.create_preset(USER, "混ぜる", [theirs.id])
    with pytest.raises(NotFoundError):
        w.calendars.reorder_calendars(USER, [theirs.id])
    assert w.calendar_repo.find_by_id(theirs.id).name == "他人"
    assert [c.name for c in _events_only(w.calendars.list_calendars(USER))] == ["予定"]


def test_deleting_moves_events_to_the_default_calendar(w: World) -> None:
    default_id = w.default_id()
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    event = w.single(calendar_id=work.id)
    assert event.calendar_id == work.id
    before = event.version

    moved = w.calendars.delete_calendar(work.id, USER)

    assert moved == 1
    after = w.uc.get_event(event.id, USER)
    assert after.calendar_id == default_id
    assert after.version == before + 1
    assert w.calendar_repo.find_by_id(work.id) is None


def test_the_default_calendar_cannot_be_deleted(w: World) -> None:
    with pytest.raises(ConflictError):
        w.calendars.delete_calendar(w.default_id(), USER)


def test_reorder_puts_the_given_ones_first(w: World) -> None:
    default_id = w.default_id()
    a = w.calendars.create_calendar(USER, "A", EventColorKey.DEFAULT)
    b = w.calendars.create_calendar(USER, "B", EventColorKey.DEFAULT)
    listed = w.calendars.reorder_calendars(USER, [b.id])
    assert [c.id for c in _events_only(listed)] == [b.id, default_id, a.id]


# ── 表示の選択・組み合わせ ──────────────────────────────────────────────


def test_visibility_replaces_the_whole_selection(w: World) -> None:
    default_id = w.default_id()
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    listed = _events_only(w.calendars.set_visible_calendars(USER, [work.id]))
    assert {c.id: c.is_visible for c in listed} == {default_id: False, work.id: True}
    # 覚えている（読み直しても同じ）
    assert {c.id: c.is_visible for c in _events_only(w.calendars.list_calendars(USER))} == {
        default_id: False, work.id: True,
    }


def test_preset_shows_only_its_calendars_and_forgets_deleted_ones(w: World) -> None:
    default_id = w.default_id()
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    home = w.calendars.create_calendar(USER, "家", EventColorKey.BASIL)
    preset = w.calendars.create_preset(USER, "仕事だけ", [work.id, work.id, home.id])
    assert preset.calendar_ids == (work.id, home.id)

    applied = _events_only(w.calendars.apply_preset(preset.id, USER))
    assert {c.id: c.is_visible for c in applied} == {
        default_id: False, work.id: True, home.id: True,
    }

    w.calendars.delete_calendar(home.id, USER)
    assert w.calendars.list_presets(USER)[0].calendar_ids == (work.id,)


def test_other_users_preset_cannot_be_applied(w: World) -> None:
    theirs = w.calendars.create_preset(OTHER_USER, "他人", [])
    with pytest.raises(NotFoundError):
        w.calendars.apply_preset(theirs.id, USER)
    with pytest.raises(NotFoundError):
        w.calendars.delete_preset(theirs.id, USER)


# ── 予定とカレンダー ────────────────────────────────────────────────────


def test_event_goes_to_the_default_calendar_when_none_is_given(w: World) -> None:
    event = w.single()
    assert event.calendar_id == w.default_id()


def test_event_cannot_be_put_into_another_users_calendar(w: World) -> None:
    theirs = w.calendars.create_calendar(OTHER_USER, "他人", EventColorKey.BASIL)
    with pytest.raises(NotFoundError):
        w.single(calendar_id=theirs.id)
    mine = w.single()
    with pytest.raises(NotFoundError):
        w.uc.update_event(
            UpdateEventCommand(event_id=mine.id, user_id=USER, title="会議", calendar_id=theirs.id)
        )
    assert w.uc.get_event(mine.id, USER).calendar_id == w.default_id()


def test_editing_moves_the_event_and_omitting_keeps_it(w: World) -> None:
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    event = w.single()
    moved = w.uc.update_event(
        UpdateEventCommand(event_id=event.id, user_id=USER, title="会議", calendar_id=work.id)
    )
    assert moved.calendar_id == work.id
    kept = w.uc.update_event(UpdateEventCommand(event_id=event.id, user_id=USER, title="会議2"))
    assert kept.calendar_id == work.id


def test_split_occurrence_keeps_the_series_calendar(w: World) -> None:
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    series = w.uc.create_recurring_event(
        CreateRecurringEventCommand(
            user_id=USER, title="定例", time_zone="Asia/Tokyo",
            anchor_utc=utc(2026, 10, 5, 9, 0), duration_minutes=60,
            recurrence_rule=weekly_rule(Weekday.MONDAY), calendar_id=work.id,
        )
    )
    single = w.uc.split_this_occurrence(
        SplitThisOccurrenceCommand(
            event_id=series.id, user_id=USER,
            occurrence_key=OccurrenceKey(date(2026, 10, 12), series.series_start_time()),
            title="定例（臨時）", start_utc=utc(2026, 10, 12, 10, 0), duration_minutes=60,
        )
    )
    assert single.calendar_id == work.id


def test_occurrences_carry_the_calendar_and_its_color(w: World) -> None:
    work = w.calendars.create_calendar(USER, "仕事", EventColorKey.TOMATO)
    w.single(calendar_id=work.id)
    w.single()
    views = w.uc.list_occurrence_views(USER, date(2026, 10, 5), date(2026, 10, 5), "Asia/Tokyo")
    assert sorted((v.calendar_id, v.calendar_color_key) for v in views) == sorted(
        [(work.id, EventColorKey.TOMATO), (w.default_id(), EventColorKey.DEFAULT)]
    )
