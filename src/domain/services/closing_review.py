"""締めの画面で気付かせる物を探す（task #161 / ADR-0011）。

- 止め忘れ（長すぎる）: ``TimeEntry.is_long_running``（12 時間超）
- 重なり: 同じ利用者の打刻どうしが時間で重なっている
- 予定はあったのに打刻が無い: 予定の回の時間に、掛かる打刻が 1 本も無い

未割当（タスクが無い・消えた）はタスクの持ち主を引く必要があるので、ユースケースで数える。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.entities.time_entry import TimeEntry


@dataclass(frozen=True)
class EntryOverlap:
    first_entry_id: int
    second_entry_id: int
    overlap: timedelta


def find_overlaps(entries: Sequence[TimeEntry], now: datetime) -> list[EntryOverlap]:
    """重なっている打刻の組（始まりの早い方が ``first``）。長さ 0 の接し方は重なりにしない。"""
    ordered = sorted(
        (e for e in entries if e.id is not None), key=lambda e: (e.started_at, e.id or 0)
    )
    found: list[EntryOverlap] = []
    for i, a in enumerate(ordered):
        a_end = _end(a, now)
        for b in ordered[i + 1 :]:
            if b.started_at >= a_end:
                break
            overlap = min(a_end, _end(b, now)) - b.started_at
            if overlap > timedelta(0):
                assert a.id is not None and b.id is not None
                found.append(EntryOverlap(a.id, b.id, overlap))
    return found


def is_uncovered(
    start: datetime, end: datetime, entries: Sequence[TimeEntry], now: datetime
) -> bool:
    """``[start, end)`` に掛かる打刻が 1 本も無いか。"""
    return not any(e.started_at < end and _end(e, now) > start for e in entries)


def _end(entry: TimeEntry, now: datetime) -> datetime:
    return entry.ended_at if entry.ended_at is not None else max(now, entry.started_at)


__all__ = ["EntryOverlap", "find_overlaps", "is_uncovered"]
