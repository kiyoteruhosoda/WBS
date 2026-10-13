from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.work_break import WorkBreak, WorkBreakSource


class WorkBreakRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def find_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[WorkBreak]:
        """``[start, end)`` に掛かる休みを始まりの順に。"""

    @abstractmethod
    def replace(
        self,
        user_id: int,
        source: WorkBreakSource,
        start: datetime,
        end: datetime,
        breaks: list[WorkBreak],
    ) -> list[WorkBreak]:
        """``[start, end)`` に始まる ``source`` の休みを消して、``breaks`` を入れる（始まりの順に返す）。"""
