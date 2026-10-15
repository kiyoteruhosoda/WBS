from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.pc_activity import PcActivityDay, PcActivitySpan


class PcActivityRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def replace_day(self, day: PcActivityDay) -> PcActivityDay:
        """``day.user_id`` の ``day.local_date`` の日を ``day``（区間も）で置き換える（区間は始まりの順に返す）。"""

    @abstractmethod
    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[PcActivitySpan]:
        """``[start, end)`` に掛かる区間を始まりの順に。"""

    @abstractmethod
    def last_updated_at(self, user_id: int, start: datetime, end: datetime) -> datetime | None:
        """``[start, end)`` に掛かる日のうち、最後に受けた時刻。1 日も無ければ ``None``。"""

    @abstractmethod
    def delete_days_ended_before(self, user_id: int, cutoff: datetime) -> None:
        """``cutoff`` までに終わった日を区間ごと消す。"""
