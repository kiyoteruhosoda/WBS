"""打刻（TimeEntry）のドメインの規則。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.domain.entities.time_entry import LONG_RUNNING_THRESHOLD, TimeEntry
from src.domain.exceptions import ValidationError

T0 = datetime(2026, 10, 1, 0, 0)


def _running(at: datetime = T0) -> TimeEntry:
    return TimeEntry.start(user_id=1, at=at, task_id=None)


def test_a_started_entry_is_running_until_stopped() -> None:
    entry = _running()
    assert entry.is_running
    entry.stop(T0 + timedelta(minutes=30))
    assert not entry.is_running
    assert entry.ended_at == T0 + timedelta(minutes=30)


def test_stop_is_idempotent() -> None:
    entry = _running()
    entry.stop(T0 + timedelta(minutes=30))
    entry.stop(T0 + timedelta(hours=5))
    assert entry.ended_at == T0 + timedelta(minutes=30)


def test_stop_before_the_start_does_not_make_a_negative_length() -> None:
    entry = _running()
    entry.stop(T0 - timedelta(seconds=5))
    assert entry.ended_at == T0
    assert entry.duration(T0 + timedelta(hours=1)) == timedelta(0)


def test_running_duration_counts_up_to_now() -> None:
    entry = _running()
    assert entry.duration(T0 + timedelta(minutes=90)) == timedelta(minutes=90)


def test_long_running_mark_starts_after_twelve_hours() -> None:
    entry = _running()
    assert not entry.is_long_running(T0 + LONG_RUNNING_THRESHOLD)
    assert entry.is_long_running(T0 + LONG_RUNNING_THRESHOLD + timedelta(seconds=1))


def test_a_stopped_long_entry_keeps_its_mark() -> None:
    entry = _running()
    entry.stop(T0 + timedelta(hours=13))
    assert entry.is_long_running(T0 + timedelta(days=3))


def test_reschedule_rejects_an_end_not_after_the_start() -> None:
    entry = _running()
    entry.stop(T0 + timedelta(hours=1))
    with pytest.raises(ValidationError):
        entry.reschedule(started_at=T0, ended_at=T0, now=T0 + timedelta(days=1))


def test_reschedule_rejects_future_times() -> None:
    entry = _running()
    with pytest.raises(ValidationError):
        entry.reschedule(started_at=T0 + timedelta(hours=2), ended_at=None, now=T0 + timedelta(hours=1))
    with pytest.raises(ValidationError):
        entry.reschedule(
            started_at=T0, ended_at=T0 + timedelta(hours=2), now=T0 + timedelta(hours=1)
        )


def test_a_stopped_entry_cannot_be_made_running_again() -> None:
    entry = _running()
    entry.stop(T0 + timedelta(hours=1))
    with pytest.raises(ValidationError):
        entry.reschedule(started_at=T0, ended_at=None, now=T0 + timedelta(days=1))


def test_overlap_counts_an_entry_that_crosses_midnight_on_both_days() -> None:
    # 23:00〜翌 1:00（UTC で考える）
    entry = _running(datetime(2026, 10, 1, 23, 0))
    entry.stop(datetime(2026, 10, 2, 1, 0))
    day1 = (datetime(2026, 10, 1), datetime(2026, 10, 2))
    day2 = (datetime(2026, 10, 2), datetime(2026, 10, 3))
    assert entry.overlaps(*day1)
    assert entry.overlaps(*day2)


def test_an_entry_ending_exactly_at_the_period_start_is_not_in_it() -> None:
    entry = _running(datetime(2026, 10, 1, 23, 0))
    entry.stop(datetime(2026, 10, 2, 0, 0))
    assert not entry.overlaps(datetime(2026, 10, 2), datetime(2026, 10, 3))


def test_a_running_entry_overlaps_every_later_period() -> None:
    entry = _running(datetime(2026, 10, 1, 9, 0))
    assert entry.overlaps(datetime(2026, 10, 5), datetime(2026, 10, 6))
    assert not entry.overlaps(datetime(2026, 9, 30), datetime(2026, 10, 1))
