"""締めのユースケース（task #161）: 確定と work_logs・確定後の保護・開け直し・未確定の期間・補正。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from src.application.dto.calendar_event_dto import OccurrenceView
from src.application.dto.time_entry_dto import (
    CreateTimeEntryCommand,
    EntryFromOccurrenceCommand,
    MergeTimeEntriesCommand,
    StartTimerCommand,
    UpdateTimeEntryCommand,
)
from src.application.use_cases.closing_use_cases import ClosingUseCases, hours_of
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.time_entry_source import TimeEntrySource
from src.domain.value_objects.work_log_source import WorkLogSource
from tests.unit.application.scheduling.fakes import FakeClock, FakeTasks, RecordingUnitOfWork
from tests.unit.application.time_tracking.fakes import (
    InMemoryClosingPeriodRepository,
    InMemoryTimeEntryRepository,
    InMemoryWorkLogRepository,
)

ME = 1
OTHER = 2
TASK_A = 10
TASK_B = 11
OTHERS_TASK = 20
TOKYO = "Asia/Tokyo"
OCT_1 = date(2026, 10, 1)
OCT_16 = date(2026, 10, 16)
NOW = datetime(2026, 10, 20, 3, 0)  # JST 10/20 12:00（後半の期間の途中）


def _jst(day: int, hour: int, minute: int = 0) -> datetime:
    """JST の 10 月 ``day`` 日 ``hour``:``minute`` を naive な UTC で。"""
    return datetime(2026, 10, day, hour, minute) - timedelta(hours=9)


class FakeOccurrences:
    def __init__(self) -> None:
        self.views: list[OccurrenceView] = []

    def add(
        self, event_id: int, start: datetime, minutes: int, task_id: int | None, all_day=False
    ) -> OccurrenceView:
        local = start + timedelta(hours=9)
        view = OccurrenceView(
            event_id=event_id,
            event_version=1,
            is_recurring=False,
            title=f"event {event_id}",
            start_utc=start,
            duration_minutes=minutes,
            date=local.date(),
            start_time=time(local.hour, local.minute),
            is_all_day=all_day,
            color_key=EventColorKey.DEFAULT,
            location=None,
            task_id=task_id,
            is_moved=False,
            is_overridden=False,
            series_key=None,
        )
        self.views.append(view)
        return view

    def list_occurrence_views(self, user_id, from_date, to_date, viewer_time_zone):
        if user_id != ME:
            return []
        return [
            v
            for v in self.views
            if from_date <= v.start_utc.date() <= to_date or (from_date <= v.date <= to_date)
        ]


class World:
    def __init__(self) -> None:
        self.clock = FakeClock(NOW)
        self.entries = InMemoryTimeEntryRepository()
        self.periods = InMemoryClosingPeriodRepository()
        self.work_logs = InMemoryWorkLogRepository()
        self.tasks = FakeTasks({TASK_A: ME, TASK_B: ME, OTHERS_TASK: OTHER})
        self.uow = RecordingUnitOfWork()
        self.occurrences = FakeOccurrences()
        self.timer = TimeEntryUseCases(
            self.entries,
            self.tasks,
            self.uow,
            closing_periods=self.periods,
            occurrences=self.occurrences,
            now=self.clock,
        )
        self.closing = ClosingUseCases(
            self.periods,
            self.entries,
            self.work_logs,
            self.tasks,
            self.uow,
            occurrences=self.occurrences,
            now=self.clock,
        )

    def entry(
        self,
        start: datetime,
        end: datetime | None,
        task_id: int | None = TASK_A,
        user_id: int = ME,
    ) -> int:
        saved = self.entries.save(
            TimeEntry(id=None, user_id=user_id, started_at=start, ended_at=end, task_id=task_id)
        )
        assert saved.id is not None
        return saved.id


@pytest.fixture
def w() -> World:
    return World()


# ── 確定と work_logs ─────────────────────────────────────────────────


def test_close_creates_work_logs_per_task_and_local_day(w: World) -> None:
    w.entry(_jst(2, 9), _jst(2, 12))  # A: 10/2 3h
    w.entry(_jst(2, 13), _jst(2, 13, 20), task_id=TASK_B)  # B: 10/2 20m
    w.entry(_jst(2, 23), _jst(3, 1, 30))  # A: 10/2 1h + 10/3 1.5h（0:00 で割る）
    w.entry(_jst(15, 23), _jst(16, 2))  # A: 10/15 1h（10/16 の 2h は後半の期間）

    result = w.closing.close(ME, OCT_1, TOKYO)

    logs = {(wl.task_id, wl.work_date): wl for wl in result.work_logs}
    assert {k: v.duration_seconds for k, v in logs.items()} == {
        (TASK_A, date(2026, 10, 2)): 4 * 3600,
        (TASK_B, date(2026, 10, 2)): 20 * 60,
        (TASK_A, date(2026, 10, 3)): 90 * 60,
        (TASK_A, date(2026, 10, 15)): 3600,
    }
    assert logs[(TASK_B, date(2026, 10, 2))].hours == Decimal("0.33")
    assert all(wl.source is WorkLogSource.CLOSING for wl in result.work_logs)
    assert {wl.closing_period_id for wl in result.work_logs} == {result.state.closed.id}
    assert result.state.starts_at == datetime(2026, 9, 30, 15)
    assert result.state.ends_at == datetime(2026, 10, 15, 15)
    assert w.uow.commits == 1


def test_close_keeps_hand_written_work_logs(w: World) -> None:
    from src.domain.entities.work_log import WorkLog

    manual = w.work_logs.save(
        WorkLog(
            id=None, user_id=ME, task_id=TASK_A, work_date=date(2026, 10, 2), hours=Decimal("2")
        )
    )
    w.entry(_jst(2, 9), _jst(2, 10))
    closed = w.closing.close(ME, OCT_1, TOKYO)
    w.closing.reopen(ME, OCT_1)

    remaining = w.work_logs.all()
    assert [wl.id for wl in remaining] == [manual.id]
    assert closed.work_logs[0].id != manual.id


def test_close_is_not_rounded(w: World) -> None:
    w.entry(_jst(2, 9), _jst(2, 9, 7) + timedelta(seconds=13))
    result = w.closing.close(ME, OCT_1, TOKYO)
    assert [wl.duration_seconds for wl in result.work_logs] == [7 * 60 + 13]
    assert hours_of(7 * 60 + 13) == Decimal("0.12")


def test_close_ignores_other_users_entries(w: World) -> None:
    w.entry(_jst(2, 9), _jst(2, 10))
    w.entry(_jst(2, 9), _jst(2, 18), task_id=OTHERS_TASK, user_id=OTHER)
    w.entry(_jst(3, 9), _jst(3, 10), task_id=None, user_id=OTHER)  # 他人の未割当は関係ない

    result = w.closing.close(ME, OCT_1, TOKYO)

    assert [(wl.user_id, wl.task_id, wl.duration_seconds) for wl in result.work_logs] == [
        (ME, TASK_A, 3600)
    ]
    # 他人の打刻は確定の後も触れる（他人の期間は確定していない）
    w.timer.delete(2, OTHER)


def test_close_refuses_while_an_entry_is_running_in_the_period(w: World) -> None:
    w.clock.current = _jst(10, 12)
    w.entry(_jst(10, 9), None)
    with pytest.raises(ConflictError):
        w.closing.close(ME, OCT_1, TOKYO)
    assert w.periods.list_first_days(ME) == set()


def test_close_refuses_unassigned_entries(w: World) -> None:
    w.entry(_jst(2, 9), _jst(2, 10))
    unassigned = w.entry(_jst(3, 9), _jst(3, 10), task_id=None)
    with pytest.raises(ConflictError, match=str(unassigned)):
        w.closing.close(ME, OCT_1, TOKYO)
    w.timer.assign_task(ME, [unassigned], TASK_B)
    w.closing.close(ME, OCT_1, TOKYO)


def test_close_twice_is_a_conflict(w: World) -> None:
    w.closing.close(ME, OCT_1, TOKYO)
    with pytest.raises(ConflictError):
        w.closing.close(ME, OCT_1, TOKYO)


def test_a_period_that_has_not_started_cannot_be_closed(w: World) -> None:
    with pytest.raises(ValidationError):
        w.closing.close(ME, date(2026, 11, 1), TOKYO)


def test_the_current_period_can_be_closed_early(w: World) -> None:
    w.entry(_jst(16, 9), _jst(16, 10))
    w.closing.close(ME, OCT_16, TOKYO)
    # その後の Start は確定済みの期間の中なので断る
    with pytest.raises(ConflictError):
        w.timer.start(StartTimerCommand(user_id=ME))


def test_a_period_is_pointed_at_by_its_first_day(w: World) -> None:
    with pytest.raises(ValidationError):
        w.closing.close(ME, date(2026, 10, 2), TOKYO)


# ── 確定後の保護 ─────────────────────────────────────────────────────


@pytest.fixture
def closed(w: World) -> dict[str, int]:
    """前半（10/1〜15）を確定。境目をまたぐ打刻と、後半だけの打刻を用意する。"""
    ids = {
        "inside": w.entry(_jst(2, 9), _jst(2, 10)),
        "across": w.entry(_jst(15, 23), _jst(16, 1)),
        "after": w.entry(_jst(17, 9), _jst(17, 10)),
    }
    w.closing.close(ME, OCT_1, TOKYO)
    return ids


def test_closed_entries_cannot_be_updated_or_deleted(w: World, closed) -> None:
    for entry_id in (closed["inside"], closed["across"]):
        with pytest.raises(ConflictError):
            w.timer.update(entry_id, ME, UpdateTimeEntryCommand(memo="x"))
        with pytest.raises(ConflictError):
            w.timer.delete(entry_id, ME)
        with pytest.raises(ConflictError):
            w.timer.assign_task(ME, [entry_id], TASK_B)


def test_an_open_entry_cannot_be_moved_into_a_closed_period(w: World, closed) -> None:
    with pytest.raises(ConflictError):
        w.timer.update(closed["after"], ME, UpdateTimeEntryCommand(started_at=_jst(15, 20)))
    w.timer.update(closed["after"], ME, UpdateTimeEntryCommand(started_at=_jst(17, 8)))


def test_entries_cannot_be_added_to_a_closed_period(w: World, closed) -> None:
    with pytest.raises(ConflictError):
        w.timer.create(
            CreateTimeEntryCommand(user_id=ME, started_at=_jst(5, 9), ended_at=_jst(5, 10))
        )
    # 境目の瞬間（10/16 0:00 JST）からは後半の期間
    w.timer.create(CreateTimeEntryCommand(user_id=ME, started_at=_jst(16, 2), ended_at=_jst(16, 3)))


def test_split_and_merge_are_refused_in_a_closed_period(w: World, closed) -> None:
    with pytest.raises(ConflictError):
        w.timer.split(closed["inside"], ME, _jst(2, 9, 30))
    with pytest.raises(ConflictError):
        w.timer.merge(
            MergeTimeEntriesCommand(user_id=ME, entry_ids=[closed["across"], closed["after"]])
        )


def test_start_and_stop_are_refused_in_a_closed_period(w: World) -> None:
    w.clock.current = _jst(16, 12)
    w.timer.start(StartTimerCommand(user_id=ME, task_id=TASK_A))
    w.clock.current = _jst(20, 12)
    w.timer.stop(ME)
    # 後半を確定した後は、後半に掛かる Start / Stop を断る
    w.clock.current = _jst(31, 23)
    w.closing.close(ME, OCT_16, TOKYO)
    with pytest.raises(ConflictError):
        w.timer.start(StartTimerCommand(user_id=ME))


# ── 開け直し ─────────────────────────────────────────────────────────


def test_reopen_removes_closing_work_logs_and_unlocks_entries(w: World, closed) -> None:
    assert w.closing.work_logs_of(ME, OCT_1)
    removed = w.closing.reopen(ME, OCT_1)
    assert removed == 2  # 10/2 と 10/15
    assert w.work_logs.all() == []
    assert w.closing.work_logs_of(ME, OCT_1) == []
    w.timer.update(closed["inside"], ME, UpdateTimeEntryCommand(ended_at=_jst(2, 11)))
    again = w.closing.close(ME, OCT_1, TOKYO)
    assert sorted(wl.duration_seconds for wl in again.work_logs) == [3600, 2 * 3600]


def test_reopen_an_open_period_is_a_conflict(w: World) -> None:
    with pytest.raises(ConflictError):
        w.closing.reopen(ME, OCT_1)


def test_reopen_only_touches_my_period(w: World, closed) -> None:
    with pytest.raises(ConflictError):
        w.closing.reopen(OTHER, OCT_1)
    assert w.periods.list_first_days(ME) == {OCT_1}


# ── 分割・結合・まとめて振る ─────────────────────────────────────────


def test_split_keeps_task_and_marks_the_new_part(w: World) -> None:
    entry_id = w.entry(_jst(17, 9), _jst(17, 12))
    result = w.timer.split(entry_id, ME, _jst(17, 10))
    assert (result.first.entry.started_at, result.first.entry.ended_at) == (
        _jst(17, 9),
        _jst(17, 10),
    )
    assert (result.second.entry.started_at, result.second.entry.ended_at) == (
        _jst(17, 10),
        _jst(17, 12),
    )
    assert result.second.entry.task_id == TASK_A
    assert result.second.entry.source is TimeEntrySource.SPLIT


def test_split_a_running_entry_keeps_the_second_part_running(w: World) -> None:
    w.clock.current = _jst(17, 12)
    entry_id = w.entry(_jst(17, 9), None)
    result = w.timer.split(entry_id, ME, _jst(17, 10))
    assert result.first.entry.ended_at == _jst(17, 10)
    assert result.second.entry.is_running
    assert w.entries.find_running(ME).id == result.second.entry.id


@pytest.mark.parametrize("hour", [9, 12, 13])
def test_split_must_be_strictly_inside(w: World, hour: int) -> None:
    entry_id = w.entry(_jst(17, 9), _jst(17, 12))
    with pytest.raises(ValidationError):
        w.timer.split(entry_id, ME, _jst(17, hour))


def test_merge_joins_entries_and_the_gap(w: World) -> None:
    a = w.entry(_jst(17, 9), _jst(17, 10), task_id=None)
    b = w.entry(_jst(17, 10, 30), _jst(17, 12), task_id=TASK_B)
    merged = w.timer.merge(MergeTimeEntriesCommand(user_id=ME, entry_ids=[b, a]))
    assert merged.entry.id == a
    assert (merged.entry.started_at, merged.entry.ended_at) == (_jst(17, 9), _jst(17, 12))
    assert merged.entry.task_id == TASK_B
    assert w.entries.find_by_id(b) is None


def test_merge_needs_two_stopped_entries(w: World) -> None:
    a = w.entry(_jst(17, 9), _jst(17, 10))
    with pytest.raises(ValidationError):
        w.timer.merge(MergeTimeEntriesCommand(user_id=ME, entry_ids=[a, a]))
    w.clock.current = _jst(17, 12)
    b = w.entry(_jst(17, 11), None)
    with pytest.raises(ValidationError):
        w.timer.merge(MergeTimeEntriesCommand(user_id=ME, entry_ids=[a, b]))


def test_others_entries_cannot_be_split_merged_or_assigned(w: World) -> None:
    mine = w.entry(_jst(17, 9), _jst(17, 10))
    theirs = w.entry(_jst(17, 11), _jst(17, 12), task_id=OTHERS_TASK, user_id=OTHER)
    with pytest.raises(NotFoundError):
        w.timer.split(theirs, ME, _jst(17, 11, 30))
    with pytest.raises(NotFoundError):
        w.timer.merge(MergeTimeEntriesCommand(user_id=ME, entry_ids=[mine, theirs]))
    with pytest.raises(NotFoundError):
        w.timer.assign_task(ME, [mine, theirs], TASK_A)
    with pytest.raises(NotFoundError):
        w.timer.assign_task(ME, [mine], OTHERS_TASK)
    untouched = w.entries.find_by_id(theirs)
    assert (untouched.task_id, untouched.ended_at) == (OTHERS_TASK, _jst(17, 12))
    assert w.entries.find_by_id(mine).task_id == TASK_A


def test_assign_task_to_many(w: World) -> None:
    ids = [w.entry(_jst(17, h), _jst(17, h + 1), task_id=None) for h in (9, 11, 13)]
    views = w.timer.assign_task(ME, ids, TASK_B)
    assert [v.entry.task_id for v in views] == [TASK_B] * 3
    assert [v.task_title for v in views] == [f"task {TASK_B}"] * 3


# ── 予定の回をそのまま打刻にする ─────────────────────────────────────


def test_an_occurrence_becomes_a_time_entry(w: World) -> None:
    occurrence = w.occurrences.add(5, _jst(17, 13), 90, TASK_B)
    view = w.timer.create_from_occurrence(
        EntryFromOccurrenceCommand(user_id=ME, event_id=5, start=occurrence.start_utc)
    )
    assert (view.entry.started_at, view.entry.ended_at) == (_jst(17, 13), _jst(17, 14, 30))
    assert view.entry.task_id == TASK_B
    assert view.entry.source is TimeEntrySource.SCHEDULE


def test_an_occurrence_that_has_not_ended_or_is_all_day_is_refused(w: World) -> None:
    future = w.occurrences.add(6, _jst(20, 11), 120, TASK_A)  # 13:00 JST に終わる。今は 12:00
    all_day = w.occurrences.add(7, _jst(17, 0), 1440, None, all_day=True)
    for o in (future, all_day):
        with pytest.raises(ValidationError):
            w.timer.create_from_occurrence(
                EntryFromOccurrenceCommand(user_id=ME, event_id=o.event_id, start=o.start_utc)
            )
    with pytest.raises(NotFoundError):
        w.timer.create_from_occurrence(
            EntryFromOccurrenceCommand(user_id=ME, event_id=99, start=_jst(17, 9))
        )


# ── 画面 1 枚分と未確定の期間 ────────────────────────────────────────


def test_board_summarises_the_period(w: World) -> None:
    w.clock.current = _jst(20, 12)
    long_one = w.entry(_jst(16, 9), _jst(17, 9))  # 24h（止め忘れ）
    unassigned = w.entry(_jst(17, 10), _jst(17, 11), task_id=None)
    w.entry(_jst(17, 10, 30), _jst(17, 12), task_id=TASK_B)  # unassigned と重なる
    w.occurrences.add(5, _jst(18, 9), 60, TASK_A)  # 打刻が無い
    w.occurrences.add(6, _jst(17, 11), 30, TASK_B)  # 打刻がある
    w.occurrences.add(7, _jst(25, 9), 60, TASK_A)  # まだ先

    board = w.closing.board(ME, OCT_16, TOKYO)

    assert board.state.closed is None
    assert len(board.entries) == 3
    assert board.findings.long_running_entry_ids == [long_one]
    assert board.findings.unassigned_entry_ids == [unassigned]
    assert [(o.first_entry_id, o.second_entry_id, o.seconds) for o in board.findings.overlaps] == [
        (unassigned, unassigned + 1, 30 * 60)
    ]
    assert [o.event_id for o in board.findings.missed_occurrences] == [5]
    totals = {(t.work_date, t.task_id): t.seconds for t in board.daily_totals}
    assert totals[(date(2026, 10, 16), TASK_A)] == 15 * 3600
    assert totals[(date(2026, 10, 17), TASK_A)] == 9 * 3600
    assert totals[(date(2026, 10, 17), None)] == 3600


def test_pending_lists_unclosed_periods_before_the_current_one(w: World) -> None:
    assert w.closing.pending(ME, TOKYO).pending == []
    w.entry(_jst(1, 9) - timedelta(days=20), _jst(1, 10) - timedelta(days=20))  # 9/11
    pending = w.closing.pending(ME, TOKYO)
    assert pending.current.first_day == OCT_16
    assert [p.first_day for p in pending.pending] == [
        date(2026, 9, 1),
        date(2026, 9, 16),
        OCT_1,
    ]
    w.closing.close(ME, date(2026, 9, 16), TOKYO)
    assert [p.first_day for p in w.closing.pending(ME, TOKYO).pending] == [
        date(2026, 9, 1),
        OCT_1,
    ]
    # 他人には関係ない
    assert w.closing.pending(OTHER, TOKYO).pending == []
