"""打刻のインメモリのリポジトリ（DB を使わない試験用）。

走っている打刻の「1 人 1 本」は、表の部分一意索引と同じく ``save`` で ``ConflictError`` にする。
"""

from __future__ import annotations

import copy
from datetime import datetime

from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError
from src.domain.repositories.time_entry_repository import TimeEntryRepository


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
