"""打刻の区間の計算（WinTrack の ``fill`` / ``override``、task #386 / ADR-0045）。

区間はすべて半開区間 ``[始まり, 終わり)``（naive な UTC）。**走っている打刻は終わりが無い**（始まり〜∞ を覆う）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.time_entry_carving import CarvingAction
from src.domain.value_objects.time_entry_source import TimeEntrySource


def free_spans(
    start: datetime, end: datetime, occupied: Iterable[TimeEntry]
) -> list[tuple[datetime, datetime]]:
    """``[start, end)`` のうち、``occupied`` のどの打刻にも覆われていない部分（始まりの順）。"""
    spans = [(start, end)]
    for entry in occupied:
        taken_start = entry.started_at
        taken_end = entry.ended_at
        next_spans: list[tuple[datetime, datetime]] = []
        for free_start, free_end in spans:
            if taken_end is not None and taken_end <= taken_start:
                next_spans.append((free_start, free_end))  # 長さ 0 の打刻は何も覆わない
                continue
            if taken_start >= free_end or (taken_end is not None and taken_end <= free_start):
                next_spans.append((free_start, free_end))
                continue
            if free_start < taken_start:
                next_spans.append((free_start, taken_start))
            if taken_end is not None and taken_end < free_end:
                next_spans.append((taken_end, free_end))
        spans = next_spans
    return sorted(spans)


@dataclass(frozen=True)
class Carving:
    """1 本の手の打刻を ``[start, end)`` で切り抜いた結果。"""

    action: CarvingAction
    # 切り抜いた後の元の打刻（消したときは None）
    remaining: TimeEntry | None
    # 例外作業の後ろに続く新しい打刻（分けた・走らせ直したとき）
    continuation: TimeEntry | None


def carve(entry: TimeEntry, start: datetime, end: datetime) -> Carving:
    """手の打刻 ``entry`` から ``[start, end)`` を切り抜く。``entry`` は区間に掛かっている前提。

    - 走っている打刻: 区間より前に始まっていれば区間の始まりで閉じ、区間の終わりから同じタスクで
      走らせ直す。区間の中で始まっていれば、始まりを区間の終わりへずらす
    - 止まった打刻: 片側に掛かれば縮める・中に収まれば消す・またげば前後の 2 本に分ける
    """
    if entry.is_running:
        if entry.started_at < start:
            closed = replace(entry, ended_at=start)
            restarted = TimeEntry(
                id=None, user_id=entry.user_id, started_at=end, task_id=entry.task_id,
                memo=entry.memo, source=TimeEntrySource.SPLIT,
            )
            return Carving(CarvingAction.RESTARTED, closed, restarted)
        return Carving(CarvingAction.SHRUNK_START, replace(entry, started_at=end), None)

    assert entry.ended_at is not None
    before = entry.started_at < start
    after = entry.ended_at > end
    if before and after:
        rest = TimeEntry(
            id=None, user_id=entry.user_id, started_at=end, ended_at=entry.ended_at,
            task_id=entry.task_id, memo=entry.memo, source=TimeEntrySource.SPLIT,
        )
        return Carving(CarvingAction.SPLIT, replace(entry, ended_at=start), rest)
    if before:
        return Carving(CarvingAction.SHRUNK_END, replace(entry, ended_at=start), None)
    if after:
        return Carving(CarvingAction.SHRUNK_START, replace(entry, started_at=end), None)
    return Carving(CarvingAction.REMOVED, None, None)


__all__ = ["Carving", "carve", "free_spans"]
