"""締めで気付かせる物（task #161）: 重なり・予定はあったのに打刻が無い。"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.domain.entities.time_entry import TimeEntry
from src.domain.services.closing_review import EntryOverlap, find_overlaps, is_uncovered

NOW = datetime(2026, 10, 2, 12, 0)


def _entry(id: int, start_h: int, end_h: int | None) -> TimeEntry:
    return TimeEntry(
        id=id,
        user_id=1,
        started_at=datetime(2026, 10, 2, start_h),
        ended_at=datetime(2026, 10, 2, end_h) if end_h is not None else None,
    )


def test_overlapping_pairs_are_found() -> None:
    entries = [_entry(1, 1, 4), _entry(2, 2, 3), _entry(3, 3, 5), _entry(4, 6, 7)]
    assert find_overlaps(entries, NOW) == [
        EntryOverlap(1, 2, timedelta(hours=1)),
        EntryOverlap(1, 3, timedelta(hours=1)),
    ]


def test_touching_entries_do_not_overlap() -> None:
    assert find_overlaps([_entry(1, 1, 2), _entry(2, 2, 3)], NOW) == []


def test_a_running_entry_overlaps_until_now() -> None:
    assert find_overlaps([_entry(1, 10, None), _entry(2, 11, 13)], NOW) == [
        EntryOverlap(1, 2, timedelta(hours=1))
    ]


def test_an_occurrence_without_any_entry_is_uncovered() -> None:
    entries = [_entry(1, 1, 2)]
    assert is_uncovered(datetime(2026, 10, 2, 3), datetime(2026, 10, 2, 4), entries, NOW)
    assert not is_uncovered(datetime(2026, 10, 2, 1, 30), datetime(2026, 10, 2, 4), entries, NOW)
    # 接しているだけでは掛からない
    assert is_uncovered(datetime(2026, 10, 2, 2), datetime(2026, 10, 2, 3), entries, NOW)
