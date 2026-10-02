"""いまの予定の回のタスク（打刻の Start の既定、ADR-0008・ADR-0009）。"""

from __future__ import annotations

from datetime import date, datetime, time

from src.application.dto.calendar_event_dto import (
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    OccurrenceCommand,
)
from src.application.use_cases.calendar_event_use_cases import CalendarEventUseCases
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.recurrence import Weekday
from tests.unit.application.scheduling.fakes import (
    FakeTasks,
    InMemoryCalendarEventRepository,
    RecordingUnitOfWork,
)
from tests.unit.domain.scheduling.support import utc, weekly_rule

USER = 1
OTHER_USER = 2
MY_TASK = 10
MY_OTHER_TASK = 11
THEIR_TASK = 20


def _use_cases(tasks: FakeTasks | None = None) -> CalendarEventUseCases:
    return CalendarEventUseCases(
        InMemoryCalendarEventRepository(),
        tasks or FakeTasks({MY_TASK: USER, MY_OTHER_TASK: USER, THEIR_TASK: OTHER_USER}),
        RecordingUnitOfWork(),
        now=lambda: datetime(2026, 5, 1),
    )


def _single(uc: CalendarEventUseCases, start: datetime, minutes: int, task_id: int | None,
            user_id: int = USER):
    return uc.create_single_event(
        CreateSingleEventCommand(
            user_id=user_id, title="s", time_zone="Asia/Tokyo", start_utc=start,
            duration_minutes=minutes, task_id=task_id,
        )
    )


def test_returns_the_task_of_the_occurrence_covering_the_instant() -> None:
    uc = _use_cases()
    _single(uc, utc(2026, 5, 20, 9, 0), 60, MY_TASK)
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 9, 0)) == MY_TASK
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 9, 59)) == MY_TASK
    # 終わりは含まない・始まる前も無い
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 10, 0)) is None
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 8, 59)) is None


def test_occurrences_without_a_task_are_ignored() -> None:
    uc = _use_cases()
    _single(uc, utc(2026, 5, 20, 9, 0), 60, None)
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 9, 30)) is None


def test_the_latest_started_occurrence_wins_when_they_overlap() -> None:
    uc = _use_cases()
    _single(uc, utc(2026, 5, 20, 0, 0), 1440, MY_OTHER_TASK)  # 終日
    _single(uc, utc(2026, 5, 20, 9, 0), 120, MY_TASK)
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 10, 0)) == MY_TASK
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 12, 0)) == MY_OTHER_TASK


def test_recurring_occurrences_count_and_skipped_ones_do_not() -> None:
    uc = _use_cases()
    event = uc.create_recurring_event(
        CreateRecurringEventCommand(
            user_id=USER, title="r", time_zone="Asia/Tokyo",
            anchor_utc=utc(2026, 5, 6, 9, 30), duration_minutes=60,
            recurrence_rule=weekly_rule(Weekday.WEDNESDAY), task_id=MY_TASK,
        )
    )
    assert uc.task_scheduled_at(USER, utc(2026, 5, 13, 10, 0)) == MY_TASK
    uc.skip_occurrence(
        OccurrenceCommand(
            event_id=event.id, user_id=USER,
            occurrence_key=OccurrenceKey(date(2026, 5, 13), time(9, 30)),
        )
    )
    assert uc.task_scheduled_at(USER, utc(2026, 5, 13, 10, 0)) is None
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 10, 0)) == MY_TASK


def test_only_my_events_and_my_live_tasks() -> None:
    tasks = FakeTasks({MY_TASK: USER, THEIR_TASK: OTHER_USER})
    uc = _use_cases(tasks)
    _single(uc, utc(2026, 5, 20, 9, 0), 60, THEIR_TASK, user_id=OTHER_USER)
    assert uc.task_scheduled_at(USER, utc(2026, 5, 20, 9, 30)) is None

    _single(uc, utc(2026, 5, 21, 9, 0), 60, MY_TASK)
    # 予定を作った後でタスクが消えた
    tasks._owners.pop(MY_TASK)
    assert uc.task_scheduled_at(USER, utc(2026, 5, 21, 9, 30)) is None
