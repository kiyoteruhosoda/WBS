"""打刻のユースケース（task #154）: 切り替え・二重 Start・Stop の冪等・既定のタスク・持ち主。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.application.dto.time_entry_dto import StartTimerCommand, UpdateTimeEntryCommand
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from tests.unit.application.scheduling.fakes import FakeClock, FakeTasks, RecordingUnitOfWork
from tests.unit.application.time_tracking.fakes import (
    FakeScheduledTasks,
    InMemoryTimeEntryRepository,
)

ME = 1
OTHER = 2
MY_TASK = 10
MY_OTHER_TASK = 11
OTHERS_TASK = 20
T0 = datetime(2026, 10, 1, 0, 0)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def entries() -> InMemoryTimeEntryRepository:
    return InMemoryTimeEntryRepository()


@pytest.fixture
def uow() -> RecordingUnitOfWork:
    return RecordingUnitOfWork()


def _use_cases(entries, uow, clock, scheduled: int | None = None) -> TimeEntryUseCases:
    return TimeEntryUseCases(
        entries,
        FakeTasks({MY_TASK: ME, MY_OTHER_TASK: ME, OTHERS_TASK: OTHER}),
        uow,
        scheduled_tasks=FakeScheduledTasks(scheduled),
        now=clock,
    )


@pytest.fixture
def uc(entries, uow, clock) -> TimeEntryUseCases:
    return _use_cases(entries, uow, clock)


# ── Start / Stop ────────────────────────────────────────────────────────


def test_start_then_stop(uc, clock) -> None:
    started = uc.start(StartTimerCommand(user_id=ME, task_id=MY_TASK)).started
    assert started.entry.is_running
    assert started.entry.started_at == T0
    assert started.task_title == f"task {MY_TASK}"

    clock.current = T0 + timedelta(minutes=25)
    stopped = uc.stop(ME)
    assert stopped is not None
    assert stopped.entry.ended_at == T0 + timedelta(minutes=25)
    assert stopped.duration_seconds == 25 * 60
    assert uc.current(ME) is None


def test_start_while_running_switches_at_the_same_instant(uc, entries, clock) -> None:
    first = uc.start(StartTimerCommand(user_id=ME, task_id=MY_TASK)).started
    clock.current = T0 + timedelta(minutes=40)

    result = uc.start(StartTimerCommand(user_id=ME, task_id=MY_OTHER_TASK))

    assert result.stopped is not None
    assert result.stopped.entry.id == first.entry.id
    assert result.stopped.entry.ended_at == T0 + timedelta(minutes=40)
    assert result.started.entry.started_at == T0 + timedelta(minutes=40)
    assert result.started.entry.task_id == MY_OTHER_TASK
    running = [e for e in entries.all() if e.is_running]
    assert [e.id for e in running] == [result.started.entry.id]


def test_double_start_keeps_one_running_entry(uc, entries, clock) -> None:
    uc.start(StartTimerCommand(user_id=ME))
    uc.start(StartTimerCommand(user_id=ME))
    assert sum(1 for e in entries.all() if e.is_running) == 1
    assert len(entries.all()) == 2


def test_switch_commits_once(entries, uow, clock) -> None:
    uc = _use_cases(entries, uow, clock)
    uc.start(StartTimerCommand(user_id=ME))
    before = uow.commits
    uc.start(StartTimerCommand(user_id=ME))
    assert uow.commits == before + 1


def test_stop_is_idempotent(uc, clock) -> None:
    uc.start(StartTimerCommand(user_id=ME))
    clock.current = T0 + timedelta(minutes=5)
    first = uc.stop(ME)
    clock.current = T0 + timedelta(minutes=9)
    second = uc.stop(ME)
    assert first is not None
    assert first.entry.ended_at == T0 + timedelta(minutes=5)
    assert second is None


def test_stop_without_any_entry_does_nothing(uc, uow) -> None:
    assert uc.stop(ME) is None
    assert uow.commits == 0


def test_a_second_running_row_is_refused_by_the_store(entries) -> None:
    entries.save(TimeEntry.start(user_id=ME, at=T0, task_id=None))
    with pytest.raises(ConflictError):
        entries.save(TimeEntry.start(user_id=ME, at=T0, task_id=None))


# ── 既定のタスク ────────────────────────────────────────────────────────


def test_default_task_is_unassigned_when_there_is_no_history(uc) -> None:
    assert uc.start(StartTimerCommand(user_id=ME)).started.entry.task_id is None


def test_default_task_is_the_previous_entrys_task(uc, clock) -> None:
    uc.start(StartTimerCommand(user_id=ME, task_id=MY_TASK))
    uc.stop(ME)
    clock.current = T0 + timedelta(hours=1)
    uc.start(StartTimerCommand(user_id=ME, task_id=None))  # 未割当の打刻を挟む
    uc.stop(ME)
    clock.current = T0 + timedelta(hours=2)
    assert uc.start(StartTimerCommand(user_id=ME)).started.entry.task_id == MY_TASK


def test_scheduled_task_comes_before_the_previous_task(entries, uow, clock) -> None:
    uc = _use_cases(entries, uow, clock, scheduled=MY_OTHER_TASK)
    uc.start(StartTimerCommand(user_id=ME, task_id=MY_TASK))
    uc.stop(ME)
    assert uc.start(StartTimerCommand(user_id=ME)).started.entry.task_id == MY_OTHER_TASK


def test_a_scheduled_task_of_someone_else_is_skipped(entries, uow, clock) -> None:
    uc = _use_cases(entries, uow, clock, scheduled=OTHERS_TASK)
    assert uc.start(StartTimerCommand(user_id=ME)).started.entry.task_id is None


def test_explicit_null_starts_unassigned_even_with_history(entries, uow, clock) -> None:
    uc = _use_cases(entries, uow, clock, scheduled=MY_TASK)
    assert uc.start(StartTimerCommand(user_id=ME, task_id=None)).started.entry.task_id is None


def test_cannot_start_on_someone_elses_task(uc, entries) -> None:
    with pytest.raises(NotFoundError):
        uc.start(StartTimerCommand(user_id=ME, task_id=OTHERS_TASK))
    assert entries.all() == []


# ── 他人の打刻 ──────────────────────────────────────────────────────────


def test_users_have_separate_running_entries(uc) -> None:
    uc.start(StartTimerCommand(user_id=ME))
    uc.start(StartTimerCommand(user_id=OTHER))
    mine = uc.current(ME)
    theirs = uc.current(OTHER)
    assert mine is not None and theirs is not None
    assert mine.entry.id != theirs.entry.id


def test_stop_does_not_touch_someone_elses_entry(uc) -> None:
    uc.start(StartTimerCommand(user_id=OTHER))
    assert uc.stop(ME) is None
    assert uc.current(OTHER) is not None


def test_someone_elses_entry_cannot_be_read_changed_or_deleted(uc, clock) -> None:
    theirs = uc.start(StartTimerCommand(user_id=OTHER)).started.entry
    assert theirs.id is not None
    with pytest.raises(NotFoundError):
        uc.get(theirs.id, ME)
    with pytest.raises(NotFoundError):
        uc.update(theirs.id, ME, UpdateTimeEntryCommand(memo="x"))
    with pytest.raises(NotFoundError):
        uc.delete(theirs.id, ME)
    clock.current = T0 + timedelta(hours=1)
    assert uc.list_in_period(ME, T0 - timedelta(days=1), T0 + timedelta(days=1)) == []
    assert uc.current(OTHER) is not None


# ── 期間の一覧（日をまたぐ打刻） ────────────────────────────────────────


def test_an_entry_that_crosses_midnight_is_listed_on_both_days(uc, clock) -> None:
    # JST 23:00〜翌 1:00 = UTC 14:00〜16:00。JST の日の区切りは UTC 15:00
    clock.current = datetime(2026, 10, 1, 14, 0)
    entry = uc.start(StartTimerCommand(user_id=ME)).started.entry
    clock.current = datetime(2026, 10, 1, 16, 0)
    uc.stop(ME)

    jst_oct1 = (datetime(2026, 9, 30, 15, 0), datetime(2026, 10, 1, 15, 0))
    jst_oct2 = (datetime(2026, 10, 1, 15, 0), datetime(2026, 10, 2, 15, 0))
    jst_oct3 = (datetime(2026, 10, 2, 15, 0), datetime(2026, 10, 3, 15, 0))
    assert [v.entry.id for v in uc.list_in_period(ME, *jst_oct1)] == [entry.id]
    assert [v.entry.id for v in uc.list_in_period(ME, *jst_oct2)] == [entry.id]
    assert uc.list_in_period(ME, *jst_oct3) == []


def test_a_running_entry_is_listed_and_marked_after_twelve_hours(uc, clock) -> None:
    uc.start(StartTimerCommand(user_id=ME))
    clock.current = T0 + timedelta(hours=13)
    (view,) = uc.list_in_period(ME, T0 + timedelta(hours=12), T0 + timedelta(hours=14))
    assert view.entry.is_running
    assert view.is_long_running
    current = uc.current(ME)
    assert current is not None and current.is_long_running


def test_period_must_not_be_empty(uc) -> None:
    with pytest.raises(ValidationError):
        uc.list_in_period(ME, T0, T0)


# ── 1 件の修正・削除 ────────────────────────────────────────────────────


def test_update_changes_only_what_was_sent(uc, clock) -> None:
    entry = uc.start(StartTimerCommand(user_id=ME, task_id=MY_TASK, memo="m")).started.entry
    clock.current = T0 + timedelta(hours=2)
    uc.stop(ME)
    assert entry.id is not None

    view = uc.update(
        entry.id, ME, UpdateTimeEntryCommand(ended_at=T0 + timedelta(hours=1), task_id=None)
    )
    assert view.entry.started_at == T0
    assert view.entry.ended_at == T0 + timedelta(hours=1)
    assert view.entry.task_id is None
    assert view.entry.memo == "m"


def test_task_of_a_running_entry_can_be_changed_in_place(uc) -> None:
    entry = uc.start(StartTimerCommand(user_id=ME)).started.entry
    assert entry.id is not None
    view = uc.update(entry.id, ME, UpdateTimeEntryCommand(task_id=MY_TASK))
    assert view.entry.is_running
    assert view.task_title == f"task {MY_TASK}"


def test_update_refuses_someone_elses_task(uc) -> None:
    entry = uc.start(StartTimerCommand(user_id=ME)).started.entry
    assert entry.id is not None
    with pytest.raises(NotFoundError):
        uc.update(entry.id, ME, UpdateTimeEntryCommand(task_id=OTHERS_TASK))


def test_delete_removes_the_entry(uc) -> None:
    entry = uc.start(StartTimerCommand(user_id=ME)).started.entry
    assert entry.id is not None
    uc.delete(entry.id, ME)
    assert uc.current(ME) is None
    with pytest.raises(NotFoundError):
        uc.get(entry.id, ME)
