"""打刻のインメモリのリポジトリ（DB を使わない試験用）。

走っている打刻の「1 人 1 本」は、表の部分一意索引と同じく ``save`` で ``ConflictError`` にする。
"""

from __future__ import annotations

import copy
from datetime import date, datetime

from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ConflictError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.repositories.work_log_repository import WorkLogRepository


class InMemoryTimeEntryRepository(TimeEntryRepository):
    def __init__(self) -> None:
        self._rows: dict[int, TimeEntry] = {}
        self._next_id = 1

    def find_by_id(self, entry_id: int) -> TimeEntry | None:
        found = self._rows.get(entry_id)
        return copy.deepcopy(found) if found is not None else None

    def find_running(self, user_id: int) -> TimeEntry | None:
        for e in self._rows.values():
            if e.user_id == user_id and e.is_running:
                return copy.deepcopy(e)
        return None

    def find_latest_task_id(self, user_id: int) -> int | None:
        with_task = [e for e in self._rows.values() if e.user_id == user_id and e.task_id is not None]
        if not with_task:
            return None
        return max(with_task, key=lambda e: (e.started_at, e.id or 0)).task_id

    def find_earliest_started_at(self, user_id: int) -> datetime | None:
        starts = [e.started_at for e in self._rows.values() if e.user_id == user_id]
        return min(starts) if starts else None

    def find_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[TimeEntry]:
        found = [
            copy.deepcopy(e) for e in self._rows.values()
            if e.user_id == user_id and e.overlaps(start, end)
        ]
        return sorted(found, key=lambda e: (e.started_at, e.id or 0))

    def save(self, entry: TimeEntry) -> TimeEntry:
        if entry.is_running:
            for other in self._rows.values():
                if other.user_id == entry.user_id and other.is_running and other.id != entry.id:
                    raise ConflictError("A time entry is already running for this user")
        if entry.id is None:
            entry.id = self._next_id
            self._next_id += 1
        self._rows[entry.id] = copy.deepcopy(entry)
        return copy.deepcopy(entry)

    def delete(self, entry_id: int) -> None:
        self._rows.pop(entry_id, None)

    def all(self) -> list[TimeEntry]:
        return [copy.deepcopy(e) for e in self._rows.values()]


class FakeScheduledTasks:
    """``ScheduledTaskLookup``。いつ聞かれても ``task_id`` を返す。"""

    def __init__(self, task_id: int | None) -> None:
        self.task_id = task_id
        self.asked: list[tuple[int, datetime]] = []

    def task_scheduled_at(self, user_id: int, at: datetime) -> int | None:
        self.asked.append((user_id, at))
        return self.task_id


class InMemoryClosingPeriodRepository(ClosingPeriodRepository):
    def __init__(self) -> None:
        self._rows: dict[int, ClosingPeriod] = {}
        self._next_id = 1

    def find_by_first_day(self, user_id: int, first_day: date) -> ClosingPeriod | None:
        for p in self._rows.values():
            if p.user_id == user_id and p.first_day == first_day:
                return copy.deepcopy(p)
        return None

    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime | None
    ) -> list[ClosingPeriod]:
        found = [
            copy.deepcopy(p) for p in self._rows.values()
            if p.user_id == user_id and p.ends_at > start and (end is None or p.starts_at < end)
        ]
        return sorted(found, key=lambda p: p.starts_at)

    def list_first_days(self, user_id: int) -> set[date]:
        return {p.first_day for p in self._rows.values() if p.user_id == user_id}

    def save(self, period: ClosingPeriod) -> ClosingPeriod:
        if self.find_by_first_day(period.user_id, period.first_day) is not None:
            raise ConflictError("This closing period is already closed")
        period.id = self._next_id
        self._next_id += 1
        self._rows[period.id] = copy.deepcopy(period)
        return copy.deepcopy(period)

    def delete(self, period_id: int) -> None:
        self._rows.pop(period_id, None)


class InMemoryWorkLogRepository(WorkLogRepository):
    def __init__(self) -> None:
        self._rows: dict[int, WorkLog] = {}
        self._next_id = 1

    def find_by_id(self, work_log_id: int) -> WorkLog | None:
        found = self._rows.get(work_log_id)
        return copy.deepcopy(found) if found is not None else None

    def find_by_task(self, task_id: int) -> list[WorkLog]:
        return [copy.deepcopy(w) for w in self._rows.values() if w.task_id == task_id]

    def save(self, work_log: WorkLog) -> WorkLog:
        if work_log.id is None:
            work_log.id = self._next_id
            self._next_id += 1
        self._rows[work_log.id] = copy.deepcopy(work_log)
        return copy.deepcopy(work_log)

    def soft_delete(self, work_log_id: int) -> None:
        self._rows.pop(work_log_id, None)

    def find_by_closing_period(self, closing_period_id: int) -> list[WorkLog]:
        found = [
            copy.deepcopy(w) for w in self._rows.values()
            if w.closing_period_id == closing_period_id
        ]
        return sorted(found, key=lambda w: (w.work_date, w.task_id, w.id or 0))

    def delete_by_closing_period(self, closing_period_id: int) -> int:
        doomed = [i for i, w in self._rows.items() if w.closing_period_id == closing_period_id]
        for i in doomed:
            del self._rows[i]
        return len(doomed)

    def all(self) -> list[WorkLog]:
        return [copy.deepcopy(w) for w in self._rows.values()]
