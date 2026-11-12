"""Ledger of seconds per (task, user's date) (visualizing actuals, task #162 / ADR-0017).

Plans, time entries and confirmed actuals are brought into the same shape, then re-summed by period, task or group.
Time without a task (unassigned time entries, plans not tied to a task) has ``task_id`` None.
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
        """(task, day, seconds) ordered by day, then task (unassigned last)."""
        for (task_id, day), seconds in sorted(
            self._seconds.items(), key=lambda kv: (kv[0][1], kv[0][0] is None, kv[0][0] or 0)
        ):
            yield task_id, day, seconds

    def total(self, period: ReportPeriod, *, task_only: bool | None = None) -> int:
        """Total for the period. With ``task_only`` True only time with a task, with False only time outside tasks."""
        return sum(
            seconds
            for (task_id, day), seconds in self._seconds.items()
            if period.contains(day) and (task_only is None or (task_id is not None) is task_only)
        )

    def grouped(
        self, period: ReportPeriod, group_of: Callable[[int | None], str]
    ) -> dict[str, int]:
        """Sum the period's seconds per value of ``group_of(task_id)``."""
        totals: dict[str, int] = {}
        for (task_id, day), seconds in self._seconds.items():
            if period.contains(day):
                key = group_of(task_id)
                totals[key] = totals.get(key, 0) + seconds
        return totals

    def span_by_task(self) -> dict[int, tuple[date, date]]:
        """First and last day per task (time outside tasks is not included)."""
        spans: dict[int, tuple[date, date]] = {}
        for task_id, day in self._seconds:
            if task_id is None:
                continue
            first, last = spans.get(task_id, (day, day))
            spans[task_id] = (min(first, day), max(last, day))
        return spans


__all__ = ["DailyLedger", "LedgerKey"]
