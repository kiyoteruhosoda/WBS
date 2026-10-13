"""打刻を利用者の日付ごと・タスクごとの長さに割る（締め、task #161 / ADR-0012）。

日をまたぐ打刻は利用者のタイムゾーンの 0:00 で割って、それぞれの日へ入れる（#163）。
期間の外にはみ出した部分は数えない（隣の期間の締めで数える）。丸めない。
休み（task #392 / ADR-0048）と重なる時間は数えない（実績の長さ = 打刻の長さ − その打刻と重なる休み）。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, tzinfo

from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.work_break import WorkBreak
from src.domain.value_objects.half_month_period import local_date_of, local_midnight_utc

DailyKey = tuple[int | None, date]
"""（タスク（未割当は None）, 利用者の日付）。"""


def allocate_by_local_day(
    entries: Iterable[TimeEntry],
    window_start: datetime,
    window_end: datetime,
    zone: tzinfo,
    now: datetime,
    breaks: Iterable[WorkBreak] = (),
) -> dict[DailyKey, timedelta]:
    """``[window_start, window_end)`` の中の長さを（タスク, 日）ごとに足し上げる。

    走っている打刻は ``now`` までを数える（画面の合計のため。確定では走っている打刻を断る）。
    ``breaks`` と重なる時間は数えない。長さ 0 の部分は入れない。
    """
    totals: dict[DailyKey, timedelta] = {}
    rests = sorted((b.started_at, b.ended_at) for b in breaks if b.ended_at > b.started_at)
    for entry in entries:
        end = entry.ended_at if entry.ended_at is not None else max(now, entry.started_at)
        for piece_start, piece_end in _without_breaks(entry.started_at, end, rests):
            _add_by_local_day(
                totals, entry.task_id, max(piece_start, window_start),
                min(piece_end, window_end), zone,
            )
    return totals


def _without_breaks(
    start: datetime, end: datetime, rests: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    """``[start, end)`` から休みの時間を除いた部分（始まりの順）。"""
    pieces = [(start, end)]
    for rest_start, rest_end in rests:
        if rest_start >= end:
            break
        next_pieces: list[tuple[datetime, datetime]] = []
        for piece_start, piece_end in pieces:
            if rest_end <= piece_start or rest_start >= piece_end:
                next_pieces.append((piece_start, piece_end))
                continue
            if piece_start < rest_start:
                next_pieces.append((piece_start, rest_start))
            if rest_end < piece_end:
                next_pieces.append((rest_end, piece_end))
        pieces = next_pieces
    return pieces


def _add_by_local_day(
    totals: dict[DailyKey, timedelta],
    task_id: int | None,
    cursor: datetime,
    stop: datetime,
    zone: tzinfo,
) -> None:
    """``[cursor, stop)`` を利用者の 0:00 で割って足す。"""
    while cursor < stop:
        day = local_date_of(cursor, zone)
        boundary = local_midnight_utc(day + timedelta(days=1), zone)
        if boundary <= cursor:  # 夏時間の境目などで戻らないように
            boundary = cursor + timedelta(days=1)
        segment_end = min(stop, boundary)
        key = (task_id, day)
        totals[key] = totals.get(key, timedelta(0)) + (segment_end - cursor)
        cursor = segment_end


def whole_seconds(length: timedelta) -> int:
    """秒にする（秒未満は四捨五入。打刻は秒まで持つ前提で、ここでは単位をそろえるだけ）。"""
    return round(length.total_seconds())


__all__ = ["DailyKey", "allocate_by_local_day", "whole_seconds"]
