from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.time_entry_carving import TimeEntryCarving


class TimeEntryCarvingRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def add(self, carving: TimeEntryCarving) -> TimeEntryCarving: ...

    @abstractmethod
    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[TimeEntryCarving]:
        """例外作業の区間が ``[start, end)`` に掛かる記録を、切り抜いた順に。"""
