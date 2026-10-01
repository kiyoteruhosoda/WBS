"""打刻を利用者の日付ごと・タスクごとの長さに割る（締め、task #161 / ADR-0011）。

日をまたぐ打刻は利用者のタイムゾーンの 0:00 で割って、それぞれの日へ入れる（#163）。
期間の外にはみ出した部分は数えない（隣の期間の締めで数える）。丸めない。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from src.domain.entities.time_entry import TimeEntry
from src.domain.value_objects.half_month_period import local_date_of, local_midnight_utc

DailyKey = tuple[int | None, date]
"""（タスク（未割当は None）, 利用者の日付）。"""


def allocate_by_local_day(
    entries: Iterable[TimeEntry],
    window_start: datetime,
    window_end: datetime,
    zone: tzinfo,
    now: datetime,
) -> dict[DailyKey, timedelta]:
    """``[window_start, window_end)`` の中の長さを（タスク, 日）ごとに足し上げる。

    走っている打刻は ``now`` までを数える（画面の合計のため。確定では走っている打刻を断る）。
    長さ 0 の部分は入れない。
    """
    totals: dict[DailyKey, timedelta] = {}
    for entry in entries:
        end = entry.ended_at if entry.ended_at is not None else max(now, entry.started_at)
        cursor = max(entry.started_at, window_start)
        stop = min(end, window_end)
        while cursor < stop:
            day = local_date_of(cursor, zone)
            boundary = local_midnight_utc(day + timedelta(days=1), zone)
            if boundary <= cursor:  # 夏時間の境目などで戻らないように
                boundary = cursor + timedelta(days=1)
            segment_end = min(stop, boundary)
            key = (entry.task_id, day)
            totals[key] = totals.get(key, timedelta(0)) + (segment_end - cursor)
            cursor = segment_end
    return totals


def whole_seconds(length: timedelta) -> int:
    """秒にする（秒未満は四捨五入。打刻は秒まで持つ前提で、ここでは単位をそろえるだけ）。"""
    return round(length.total_seconds())


__all__ = ["DailyKey", "allocate_by_local_day", "whole_seconds"]
