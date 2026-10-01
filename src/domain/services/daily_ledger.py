"""（タスク, 利用者の日付）ごとの秒数の帳簿（実績の見える化、task #162 / ADR-0017）。

予定・打刻・確定実績の 3 つを同じ形に揃えてから、期間・タスク・グループで足し直す。
タスクの無い時間（未割当の打刻・タスクに結ばない予定）は ``task_id`` が None。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date

from src.domain.value_objects.report_period import ReportPeriod

LedgerKey = tuple[int | None, date]


class DailyLedger:
    def __init__(self) -> None:
        self._seconds: dict[LedgerKey, int] = {}

    def add(self, task_id: int | None, day: date, seconds: int) -> None:
        if seconds <= 0:
            return
        key = (task_id, day)
        self._seconds[key] = self._seconds.get(key, 0) + seconds

    def entries(self) -> Iterator[tuple[int | None, date, int]]:
        """（タスク, 日, 秒）を日の順・タスクの順（未割当は後ろ）に。"""
        for (task_id, day), seconds in sorted(
            self._seconds.items(), key=lambda kv: (kv[0][1], kv[0][0] is None, kv[0][0] or 0)
        ):
            yield task_id, day, seconds

    def total(self, period: ReportPeriod, *, task_only: bool | None = None) -> int:
        """期間の合計。``task_only`` が True ならタスクのある分だけ、False ならタスク外だけ。"""
        return sum(
            seconds
            for (task_id, day), seconds in self._seconds.items()
            if period.contains(day) and (task_only is None or (task_id is not None) is task_only)
        )

    def grouped(
        self, period: ReportPeriod, group_of: Callable[[int | None], str]
    ) -> dict[str, int]:
        """期間の秒数を ``group_of(task_id)`` の値ごとに足す。"""
        totals: dict[str, int] = {}
        for (task_id, day), seconds in self._seconds.items():
            if period.contains(day):
                key = group_of(task_id)
                totals[key] = totals.get(key, 0) + seconds
        return totals

    def span_by_task(self) -> dict[int, tuple[date, date]]:
        """タスクごとの最初と最後の日（タスク外は載らない）。"""
        spans: dict[int, tuple[date, date]] = {}
        for task_id, day in self._seconds:
            if task_id is None:
                continue
            first, last = spans.get(task_id, (day, day))
            spans[task_id] = (min(first, day), max(last, day))
        return spans


__all__ = ["DailyLedger", "LedgerKey"]
