"""PC の自動記録（WinTrack）の打刻（task #379 / ADR-0042、Working が正: task #386 / ADR-0045）。

fill（空いている部分だけ）・override（手の打刻を切り抜く）・送り直し・締め・範囲、と Start での置き換え。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.application.dto.time_entry_dto import (
    AutoTimeEntryItem,
    AutoTimeEntryStatus,
    StartTimerCommand,
)
from src.application.use_cases.automatic_time_entry_use_cases import AutomaticTimeEntryUseCases
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.time_entry_carving import CarvingAction
from src.domain.exceptions import ConflictError, ValidationError
from src.domain.value_objects.auto_entry_mode import AutoEntryMode
from src.domain.value_objects.time_entry_source import TimeEntrySource
from tests.unit.application.scheduling.fakes import FakeClock, FakeTasks, RecordingUnitOfWork
from tests.unit.application.time_tracking.fakes import (
    InMemoryAutoTimeEntryReceiptRepository,
    InMemoryClosingPeriodRepository,
    InMemoryTimeEntryCarvingRepository,
    InMemoryTimeEntryRepository,
)

ME = 1
OTHER = 2
MY_TASK = 10
WORKING_TASK = 11
OTHERS_TASK = 20
NOW = datetime(2026, 10, 13, 12, 0)
H = timedelta(hours=1)
M = timedelta(minutes=1)


@pytest.fixture
def entries() -> InMemoryTimeEntryRepository:
    return InMemoryTimeEntryRepository()


@pytest.fixture
def receipts() -> InMemoryAutoTimeEntryReceiptRepository:
    return InMemoryAutoTimeEntryReceiptRepository()


@pytest.fixture
def carvings() -> InMemoryTimeEntryCarvingRepository:
    return InMemoryTimeEntryCarvingRepository()


@pytest.fixture
def periods() -> InMemoryClosingPeriodRepository:
    return InMemoryClosingPeriodRepository()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


TASKS = FakeTasks({MY_TASK: ME, WORKING_TASK: ME, OTHERS_TASK: OTHER})


@pytest.fixture
def uc(entries, receipts, carvings, periods, clock) -> AutomaticTimeEntryUseCases:
    return AutomaticTimeEntryUseCases(
        entries, receipts, carvings, TASKS, periods, RecordingUnitOfWork(), now=clock
    )


@pytest.fixture
def timer(entries, periods, clock) -> TimeEntryUseCases:
    return TimeEntryUseCases(
        entries, TASKS, RecordingUnitOfWork(), closing_periods=periods, now=clock
    )


def _item(ref: str, start: datetime, end: datetime, mode: str = "fill", task_id: int = MY_TASK):
    return AutoTimeEntryItem(
        client_ref=ref, started_at=start, ended_at=end, task_id=task_id, mode=mode
    )


def _manual(entries, start: datetime, end: datetime | None, memo: str | None = None) -> TimeEntry:
    return entries.save(
        TimeEntry(
            id=None, user_id=ME, started_at=start, ended_at=end, task_id=WORKING_TASK,
            memo=memo, source=TimeEntrySource.MANUAL if end else TimeEntrySource.TIMER,
        )
    )


def _spans(entries) -> list[tuple[datetime, datetime | None, str, str | None]]:
    return sorted(
        (e.started_at, e.ended_at, e.source.value, e.auto_mode.value if e.auto_mode else None)
        for e in entries.all()
    )


T0 = NOW - 5 * H


# ── fill ───────────────────────────────────────────────────────────────


def test_fill_creates_the_whole_span_when_nothing_is_there(uc, entries, receipts) -> None:
    [outcome] = uc.record(ME, [_item("a", T0, T0 + 30 * M)])
    assert (outcome.status, outcome.error) == (AutoTimeEntryStatus.CREATED, None)
    [view] = outcome.views
    assert (view.entry.started_at, view.entry.ended_at) == (T0, T0 + 30 * M)
    assert (view.entry.source, view.entry.auto_mode, view.entry.client_ref) == (
        TimeEntrySource.AUTO, AutoEntryMode.FILL, "a",
    )
    assert receipts.find(ME, "a") is not None


def test_mode_defaults_to_fill(uc) -> None:
    item = AutoTimeEntryItem(client_ref="a", started_at=T0, ended_at=T0 + M, task_id=MY_TASK)
    [outcome] = uc.record(ME, [item])
    assert outcome.views[0].entry.auto_mode is AutoEntryMode.FILL


def test_fill_only_takes_the_free_parts(uc, entries) -> None:
    _manual(entries, T0 + 10 * M, T0 + 20 * M)
    _manual(entries, T0 + 40 * M, T0 + 50 * M)
    [outcome] = uc.record(ME, [_item("a", T0, T0 + H)])
    assert outcome.status is AutoTimeEntryStatus.CREATED
    assert [(v.entry.started_at, v.entry.ended_at) for v in outcome.views] == [
        (T0, T0 + 10 * M), (T0 + 20 * M, T0 + 40 * M), (T0 + 50 * M, T0 + H),
    ]
    assert {v.entry.client_ref for v in outcome.views} == {"a"}


def test_fill_treats_the_running_entry_as_endless(uc, entries) -> None:
    _manual(entries, T0 + 30 * M, None)
    [outcome] = uc.record(ME, [_item("a", T0, T0 + 2 * H)])
    assert [(v.entry.started_at, v.entry.ended_at) for v in outcome.views] == [(T0, T0 + 30 * M)]
    [covered] = uc.record(ME, [_item("b", T0 + H, T0 + 2 * H)])
    assert (covered.status, covered.views, covered.error) == (AutoTimeEntryStatus.COVERED, [], None)


def test_covered_is_not_remembered(uc, entries, receipts) -> None:
    manual = _manual(entries, T0, T0 + H)
    assert uc.record(ME, [_item("a", T0, T0 + H)])[0].status is AutoTimeEntryStatus.COVERED
    assert receipts.find(ME, "a") is None
    # 手の打刻が消えた後に送り直すと、改めて判定して作る
    assert manual.id is not None
    entries.delete(manual.id)
    assert uc.record(ME, [_item("a", T0, T0 + H)])[0].status is AutoTimeEntryStatus.CREATED


def test_fill_does_not_cover_other_automatic_entries_either(uc) -> None:
    uc.record(ME, [_item("a", T0, T0 + 30 * M)])
    [outcome] = uc.record(ME, [_item("b", T0, T0 + H)])
    assert [(v.entry.started_at, v.entry.ended_at) for v in outcome.views] == [(T0 + 30 * M, T0 + H)]


def test_a_resent_fill_returns_all_its_pieces_and_is_not_overwritten(uc, entries) -> None:
    _manual(entries, T0 + 10 * M, T0 + 20 * M)
    [first] = uc.record(ME, [_item("a", T0, T0 + H)])
    [again] = uc.record(ME, [_item("a", T0 - H, T0 + 2 * H, mode="override")])
    assert again.status is AutoTimeEntryStatus.DUPLICATE
    assert [v.entry.id for v in again.views] == [v.entry.id for v in first.views]
    assert len(entries.all()) == 3


def test_the_same_client_ref_of_another_user_is_not_a_duplicate(uc) -> None:
    uc.record(OTHER, [_item("a", T0, T0 + M, task_id=OTHERS_TASK)])
    assert uc.record(ME, [_item("a", T0, T0 + M)])[0].status is AutoTimeEntryStatus.CREATED


# ── override ───────────────────────────────────────────────────────────


def test_override_carves_the_manual_entries(uc, entries, carvings) -> None:
    W0, W1 = T0 + H, T0 + 2 * H
    _manual(entries, T0, T0 + 70 * M, memo="前")          # 片側（後ろ）が掛かる → 終わりを縮める
    _manual(entries, T0 + 80 * M, T0 + 90 * M)           # 中に収まる → 消す
    _manual(entries, T0 + 110 * M, T0 + 3 * H)           # 片側（前）が掛かる → 始まりをずらす
    [outcome] = uc.record(ME, [_item("x", W0, W1, mode="override")])

    assert outcome.status is AutoTimeEntryStatus.CREATED
    assert [(v.entry.started_at, v.entry.auto_mode) for v in outcome.views] == [(W0, AutoEntryMode.OVERRIDE)]
    assert _spans(entries) == [
        (T0, W0, "manual", None),
        (W0, W1, "auto", "override"),
        (W1, T0 + 3 * H, "manual", None),
    ]
    assert [(c.action, c.started_at, c.ended_at) for c in carvings.rows] == [
        (CarvingAction.SHRUNK_END, T0, T0 + 70 * M),
        (CarvingAction.REMOVED, T0 + 80 * M, T0 + 90 * M),
        (CarvingAction.SHRUNK_START, T0 + 110 * M, T0 + 3 * H),
    ]
    assert carvings.rows[0].memo == "前"
    assert {(c.client_ref, c.window_started_at, c.window_ended_at) for c in carvings.rows} == {("x", W0, W1)}


def test_override_splits_a_manual_entry_that_spans_it(uc, entries, carvings) -> None:
    _manual(entries, T0, T0 + 3 * H, memo="会議")
    uc.record(ME, [_item("x", T0 + H, T0 + 2 * H, mode="override")])
    assert _spans(entries) == [
        (T0, T0 + H, "manual", None),
        (T0 + H, T0 + 2 * H, "auto", "override"),
        (T0 + 2 * H, T0 + 3 * H, "split", None),
    ]
    rest = next(e for e in entries.all() if e.source is TimeEntrySource.SPLIT)
    assert (rest.task_id, rest.memo) == (WORKING_TASK, "会議")
    assert [c.action for c in carvings.rows] == [CarvingAction.SPLIT]


def test_override_closes_and_restarts_the_running_entry(uc, entries, carvings) -> None:
    _manual(entries, T0, None)
    uc.record(ME, [_item("x", T0 + H, T0 + 2 * H, mode="override")])
    assert _spans(entries) == [
        (T0, T0 + H, "timer", None),
        (T0 + H, T0 + 2 * H, "auto", "override"),
        (T0 + 2 * H, None, "split", None),
    ]
    running = entries.find_running(ME)
    assert running is not None and running.task_id == WORKING_TASK
    assert [(c.action, c.ended_at) for c in carvings.rows] == [(CarvingAction.RESTARTED, None)]


def test_override_moves_a_running_entry_that_started_inside(uc, entries) -> None:
    _manual(entries, T0 + 90 * M, None)
    uc.record(ME, [_item("x", T0 + H, T0 + 2 * H, mode="override")])
    running = entries.find_running(ME)
    assert running is not None and running.started_at == T0 + 2 * H


def test_override_does_not_overlap_other_automatic_entries(uc, entries, carvings) -> None:
    uc.record(ME, [_item("a", T0, T0 + H)])
    _manual(entries, T0 + H, T0 + 2 * H)
    [outcome] = uc.record(ME, [_item("x", T0 + 30 * M, T0 + 90 * M, mode="override")])
    assert (outcome.status, outcome.error, outcome.views) == (
        AutoTimeEntryStatus.OVERLAP, "overlaps_automatic_entry", [],
    )
    assert carvings.rows == []
    assert len(entries.all()) == 2


# ── 締め・範囲 ──────────────────────────────────────────────────────────


def _close_until(periods, ends_at: datetime) -> None:
    periods.save(
        ClosingPeriod(
            id=None, user_id=ME, first_day=date(2026, 10, 1), last_day=ends_at.date() - timedelta(days=1),
            time_zone="UTC", starts_at=datetime(2026, 10, 1), ends_at=ends_at, closed_at=NOW,
        )
    )


def test_a_span_in_a_closed_period_is_refused(uc, periods) -> None:
    _close_until(periods, datetime(2026, 10, 13))
    for mode in ("fill", "override"):
        [outcome] = uc.record(ME, [_item(mode, datetime(2026, 10, 12, 23, 50), datetime(2026, 10, 13, 0, 10), mode)])
        assert (outcome.status, outcome.error) == (AutoTimeEntryStatus.CLOSED, "period_closed")


def test_override_does_not_carve_a_manual_entry_reaching_into_a_closed_period(uc, entries, periods, carvings) -> None:
    _close_until(periods, datetime(2026, 10, 13))
    _manual(entries, datetime(2026, 10, 12, 23, 0), datetime(2026, 10, 13, 2, 0))
    [outcome] = uc.record(ME, [_item("x", datetime(2026, 10, 13, 1, 0), datetime(2026, 10, 13, 1, 30), "override")])
    assert outcome.status is AutoTimeEntryStatus.CLOSED
    assert carvings.rows == [] and len(entries.all()) == 1


@pytest.mark.parametrize(
    ("item", "error"),
    [
        (_item("rev", NOW - H, NOW - 2 * H), "ended_not_after_started"),
        (_item("zero", NOW - H, NOW - H), "ended_not_after_started"),
        (_item("old", NOW - timedelta(days=7, seconds=1), NOW - timedelta(days=6)), "too_old"),
        (_item("future", NOW - 5 * M, NOW + 2 * M), "in_future"),
        (_item("others", NOW - 2 * H, NOW - H, task_id=OTHERS_TASK), "task_not_found"),
        (_item("missing", NOW - 2 * H, NOW - H, task_id=999), "task_not_found"),
        (_item("mode", NOW - 2 * H, NOW - H, mode="replace"), "unknown_mode"),
    ],
    ids=lambda v: v if isinstance(v, str) else v.client_ref,
)
def test_invalid_spans_are_refused_with_a_reason(uc, entries, receipts, item, error) -> None:
    [outcome] = uc.record(ME, [item])
    assert (outcome.status, outcome.error, outcome.views) == (AutoTimeEntryStatus.INVALID, error, [])
    assert entries.all() == [] and receipts.rows == {}


def test_an_end_within_the_clock_skew_is_pulled_back_to_now(uc) -> None:
    [outcome] = uc.record(ME, [_item("skew", NOW - 10 * M, NOW + timedelta(seconds=30))])
    assert outcome.views[0].entry.ended_at == NOW


def test_more_than_two_hundred_spans_are_refused_as_a_whole(uc, entries) -> None:
    items = [_item(str(i), T0 + i * M, T0 + (i + 1) * M) for i in range(201)]
    with pytest.raises(ValidationError):
        uc.record(ME, items)
    assert entries.all() == []


# ── Start が fill を置き換える ───────────────────────────────────────────


def test_start_replaces_fill_entries_after_its_time(uc, timer, entries) -> None:
    uc.record(ME, [_item("a", T0, T0 + H), _item("b", T0 + 2 * H, T0 + 3 * H)])
    result = timer.start(StartTimerCommand(user_id=ME, task_id=WORKING_TASK, at=T0 + 30 * M))
    assert result.started.entry.started_at == T0 + 30 * M
    assert _spans(entries) == [
        (T0, T0 + 30 * M, "auto", "fill"),   # at より前に始まる fill は at で縮める
        (T0 + 30 * M, None, "timer", None),  # at 以降の fill は消える
    ]


def test_start_refuses_when_an_override_is_after_its_time(uc, timer, entries) -> None:
    uc.record(ME, [_item("x", T0 + H, T0 + 2 * H, mode="override")])
    with pytest.raises(ConflictError):
        timer.start(StartTimerCommand(user_id=ME, task_id=WORKING_TASK, at=T0 + 30 * M))
    assert len(entries.all()) == 1
    # override の終わり以降からなら始められる
    timer.start(StartTimerCommand(user_id=ME, task_id=WORKING_TASK, at=T0 + 2 * H))
