"""打刻を日ごと・タスクごとに割る（task #163）: 0:00 で割る・期間の外は数えない・丸めない。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.domain.entities.time_entry import TimeEntry
from src.domain.services.daily_time_allocation import allocate_by_local_day, whole_seconds

TOKYO = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 20, 0, 0)


def _entry(
    start: datetime, end: datetime | None, task_id: int | None = 1, id: int = 1
) -> TimeEntry:
    return TimeEntry(id=id, user_id=1, started_at=start, ended_at=end, task_id=task_id)


def test_an_entry_over_midnight_is_split_at_local_midnight() -> None:
    # JST 10/2 22:30 〜 10/3 01:15（UTC 13:30 〜 16:15）
    entry = _entry(datetime(2026, 10, 2, 13, 30), datetime(2026, 10, 2, 16, 15))
    totals = allocate_by_local_day(
        [entry], datetime(2026, 9, 30, 15), datetime(2026, 10, 15, 15), TOKYO, NOW
    )
    assert totals == {
        (1, date(2026, 10, 2)): timedelta(hours=1, minutes=30),
        (1, date(2026, 10, 3)): timedelta(hours=1, minutes=15),
    }


def test_an_entry_spanning_several_days() -> None:
    entry = _entry(
        datetime(2026, 10, 1, 12), datetime(2026, 10, 3, 18)
    )  # JST 10/1 21:00 〜 10/4 3:00
    totals = allocate_by_local_day(
        [entry], datetime(2026, 9, 30, 15), datetime(2026, 10, 15, 15), TOKYO, NOW
    )
    assert totals == {
        (1, date(2026, 10, 1)): timedelta(hours=3),
        (1, date(2026, 10, 2)): timedelta(hours=24),
        (1, date(2026, 10, 3)): timedelta(hours=24),
        (1, date(2026, 10, 4)): timedelta(hours=3),
    }


def test_the_part_outside_the_period_is_left_to_the_next_period() -> None:
    # JST 10/15 23:00 〜 10/16 02:00。前半の期間（〜10/16 0:00 JST）には 1 時間だけ入る
    entry = _entry(datetime(2026, 10, 15, 14), datetime(2026, 10, 15, 17))
    first = allocate_by_local_day(
        [entry], datetime(2026, 9, 30, 15), datetime(2026, 10, 15, 15), TOKYO, NOW
    )
    second = allocate_by_local_day(
        [entry], datetime(2026, 10, 15, 15), datetime(2026, 10, 31, 15), TOKYO, NOW
    )
    assert first == {(1, date(2026, 10, 15)): timedelta(hours=1)}
    assert second == {(1, date(2026, 10, 16)): timedelta(hours=2)}


def test_entries_are_summed_by_task_and_not_rounded() -> None:
    entries = [
        _entry(datetime(2026, 10, 2, 0, 0, 0), datetime(2026, 10, 2, 0, 7, 13), task_id=1, id=1),
        _entry(datetime(2026, 10, 2, 1, 0, 0), datetime(2026, 10, 2, 1, 0, 59), task_id=1, id=2),
        _entry(datetime(2026, 10, 2, 2, 0, 0), datetime(2026, 10, 2, 2, 1, 0), task_id=2, id=3),
        _entry(datetime(2026, 10, 2, 3, 0, 0), datetime(2026, 10, 2, 3, 0, 30), task_id=None, id=4),
    ]
    totals = allocate_by_local_day(
        entries, datetime(2026, 9, 30, 15), datetime(2026, 10, 15, 15), TOKYO, NOW
    )
    assert {k: whole_seconds(v) for k, v in totals.items()} == {
        (1, date(2026, 10, 2)): 7 * 60 + 13 + 59,
        (2, date(2026, 10, 2)): 60,
        (None, date(2026, 10, 2)): 30,
    }


def test_a_running_entry_counts_until_now() -> None:
    entry = _entry(datetime(2026, 10, 19, 22), None)  # JST 10/20 7:00 から走っている
    totals = allocate_by_local_day(
        [entry], datetime(2026, 10, 15, 15), datetime(2026, 10, 31, 15), TOKYO, NOW
    )
    assert totals == {(1, date(2026, 10, 20)): timedelta(hours=2)}


def test_zero_length_entries_add_nothing() -> None:
    entry = _entry(datetime(2026, 10, 2), datetime(2026, 10, 2))
    totals = allocate_by_local_day(
        [entry], datetime(2026, 9, 30, 15), datetime(2026, 10, 15, 15), TOKYO, NOW
    )
    assert totals == {}
