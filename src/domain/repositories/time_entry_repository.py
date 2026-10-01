from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.time_entry import TimeEntry


class TimeEntryRepository(ABC):
    @abstractmethod
    def find_by_id(self, entry_id: int) -> TimeEntry | None: ...

    @abstractmethod
    def find_running(self, user_id: int) -> TimeEntry | None:
        """走っている打刻（1 人 1 本）。"""

    @abstractmethod
    def find_latest_task_id(self, user_id: int) -> int | None:
        """タスクの付いた打刻のうち、いちばん新しいもののタスク。"""

    @abstractmethod
    def find_earliest_started_at(self, user_id: int) -> datetime | None:
        """いちばん古い打刻の始まり（未確定の期間を数える起点）。"""

    @abstractmethod
    def find_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[TimeEntry]:
        """``[start, end)`` に掛かる打刻を始まりの順に。走っている打刻は終わりが無いものとして扱う。"""

    @abstractmethod
    def save(self, entry: TimeEntry) -> TimeEntry:
        """⚠ 確定（commit）はしない。走っている打刻が既にあれば ``ConflictError``。"""

    @abstractmethod
    def delete(self, entry_id: int) -> None: ...
