"""PC の自動記録（WinTrack）の打刻（task #379 / ADR-0042）: 1 区間ずつの結果・送り直し・重なり・締め。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.application.dto.time_entry_dto import (
    AutoTimeEntryItem,
    AutoTimeEntryStatus,
    StartTimerCommand,
)
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.exceptions import ValidationError
from src.domain.value_objects.time_entry_source import TimeEntrySource
from tests.unit.application.scheduling.fakes import FakeClock, FakeTasks, RecordingUnitOfWork
from tests.unit.application.time_tracking.fakes import (
    InMemoryClosingPeriodRepository,
    InMemoryTimeEntryRepository,
)

ME = 1
OTHER = 2
MY_TASK = 10
OTHERS_TASK = 20
NOW = datetime(2026, 10, 13, 12, 0)


@pytest.fixture
def entries() -> InMemoryTimeEntryRepository:
    return InMemoryTimeEntryRepository()


@pytest.fixture
def periods() -> InMemoryClosingPeriodRepository:
    return InMemoryClosingPeriodRepository()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def uc(entries, periods, clock) -> TimeEntryUseCases:
    return TimeEntryUseCases(
        entries,
        FakeTasks({MY_TASK: ME, OTHERS_TASK: OTHER}),
        RecordingUnitOfWork(),
        closing_periods=periods,
        now=clock,
    )


def _item(ref: str, start: datetime, minutes: int = 30, task_id: int = MY_TASK) -> AutoTimeEntryItem:
    return AutoTimeEntryItem(
        client_ref=ref, started_at=start, ended_at=start + timedelta(minutes=minutes), task_id=task_id
    )


def test_creates_auto_entries_with_their_client_ref(uc, entries) -> None:
    start = NOW - timedelta(hours=3)
    [outcome] = uc.record_automatic(ME, [_item("a", start)])

    assert outcome.status is AutoTimeEntryStatus.CREATED
    assert outcome.error is None
    assert outcome.view is not None
    saved = outcome.view.entry
    assert (saved.started_at, saved.ended_at) == (start, start + timedelta(minutes=30))
    assert saved.source is TimeEntrySource.AUTO
    assert saved.client_ref == "a"
    assert saved.memo is None
    assert outcome.view.task_title == f"task {MY_TASK}"
    assert len(entries.all()) == 1


def test_a_resent_entry_is_a_duplicate_and_is_not_overwritten(uc, entries) -> None:
    start = NOW - timedelta(hours=3)
    [first] = uc.record_automatic(ME, [_item("a", start)])
    # 中身が違っても、同じ client_ref は上書きしない
    [again] = uc.record_automatic(ME, [_item("a", start + timedelta(minutes=5), minutes=60)])

    assert again.status is AutoTimeEntryStatus.DUPLICATE
    assert again.view is not None and first.view is not None
    assert again.view.entry.id == first.view.entry.id
    assert again.view.entry.ended_at == start + timedelta(minutes=30)
    assert len(entries.all()) == 1


def test_the_same_client_ref_of_another_user_is_not_a_duplicate(uc) -> None:
    start = NOW - timedelta(hours=3)
    uc.record_automatic(OTHER, [_item("a", start, task_id=OTHERS_TASK)])
    [mine] = uc.record_automatic(ME, [_item("a", start)])
    assert mine.status is AutoTimeEntryStatus.CREATED


def test_one_refused_entry_does_not_stop_the_others(uc, entries) -> None:
    start = NOW - timedelta(hours=3)
    outcomes = uc.record_automatic(
        ME,
        [
            _item("a", start),
            _item("b", start + timedelta(minutes=10)),  # a と重なる
            _item("c", start + timedelta(minutes=30)),  # a のちょうど終わりから
        ],
    )
    assert [(o.client_ref, o.status, o.error) for o in outcomes] == [
        ("a", AutoTimeEntryStatus.CREATED, None),
        ("b", AutoTimeEntryStatus.OVERLAP, "overlaps_time_entry"),
        ("c", AutoTimeEntryStatus.CREATED, None),
    ]
    assert outcomes[1].view is None
    assert sorted(e.client_ref or "" for e in entries.all()) == ["a", "c"]


def test_an_entry_after_the_running_timer_started_overlaps_it(uc) -> None:
    uc.start(StartTimerCommand(user_id=ME, task_id=None, at=NOW - timedelta(hours=1)))
    [outcome] = uc.record_automatic(ME, [_item("a", NOW - timedelta(minutes=30), minutes=10)])
    assert outcome.status is AutoTimeEntryStatus.OVERLAP


def test_an_entry_in_a_closed_period_is_refused(uc, periods) -> None:
    periods.save(
        ClosingPeriod(
            id=None,
            user_id=ME,
            first_day=datetime(2026, 10, 1).date(),
            last_day=datetime(2026, 10, 12).date(),
            time_zone="UTC",
            starts_at=datetime(2026, 10, 1),
            ends_at=datetime(2026, 10, 13),
            closed_at=NOW,
        )
    )
    outcomes = uc.record_automatic(
        ME,
        [
            _item("before", datetime(2026, 10, 12, 23, 50), minutes=20),  # 締めの区切りを跨ぐ
            _item("after", datetime(2026, 10, 13, 0, 10)),
        ],
    )
    assert [(o.status, o.error) for o in outcomes] == [
        (AutoTimeEntryStatus.CLOSED, "period_closed"),
        (AutoTimeEntryStatus.CREATED, None),
    ]


@pytest.mark.parametrize(
    ("item", "error"),
    [
        (
            AutoTimeEntryItem("rev", NOW - timedelta(hours=1), NOW - timedelta(hours=2), MY_TASK),
            "ended_not_after_started",
        ),
        (
            AutoTimeEntryItem("zero", NOW - timedelta(hours=1), NOW - timedelta(hours=1), MY_TASK),
            "ended_not_after_started",
        ),
        (
            AutoTimeEntryItem("old", NOW - timedelta(days=7, seconds=1), NOW - timedelta(days=6), MY_TASK),
            "too_old",
        ),
        (
            AutoTimeEntryItem("future", NOW - timedelta(minutes=5), NOW + timedelta(minutes=2), MY_TASK),
            "in_future",
        ),
        (
            AutoTimeEntryItem("others", NOW - timedelta(hours=2), NOW - timedelta(hours=1), OTHERS_TASK),
            "task_not_found",
        ),
        (
            AutoTimeEntryItem("missing", NOW - timedelta(hours=2), NOW - timedelta(hours=1), 999),
            "task_not_found",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else v.client_ref,
)
def test_invalid_entries_are_refused_with_a_reason(uc, entries, item, error) -> None:
    [outcome] = uc.record_automatic(ME, [item])
    assert (outcome.status, outcome.error, outcome.view) == (AutoTimeEntryStatus.INVALID, error, None)
    assert entries.all() == []


def test_an_end_within_the_clock_skew_is_pulled_back_to_now(uc) -> None:
    [outcome] = uc.record_automatic(
        ME,
        [AutoTimeEntryItem("skew", NOW - timedelta(minutes=10), NOW + timedelta(seconds=30), MY_TASK)],
    )
    assert outcome.status is AutoTimeEntryStatus.CREATED
    assert outcome.view is not None
    assert outcome.view.entry.ended_at == NOW


def test_sub_second_parts_are_dropped(uc) -> None:
    start = NOW - timedelta(hours=1, microseconds=-123456)
    [outcome] = uc.record_automatic(ME, [_item("a", start)])
    assert outcome.view is not None
    assert outcome.view.entry.started_at == start.replace(microsecond=0)


def test_more_than_two_hundred_entries_are_refused_as_a_whole(uc, entries) -> None:
    start = NOW - timedelta(days=6)
    items = [_item(str(i), start + timedelta(minutes=i), minutes=1) for i in range(201)]
    with pytest.raises(ValidationError):
        uc.record_automatic(ME, items)
    assert entries.all() == []
