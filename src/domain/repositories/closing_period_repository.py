from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from src.domain.entities.closing_period import ClosingPeriod


class ClosingPeriodRepository(ABC):
    """確定した締めの期間（行がある = 確定済み）。

    ⚠ ``save`` / ``delete`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。
    """

    @abstractmethod
    def find_by_first_day(self, user_id: int, first_day: date) -> ClosingPeriod | None: ...

    @abstractmethod
    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime | None
    ) -> list[ClosingPeriod]:
        """``[start, end)`` に掛かる確定済みの期間。``end`` が None なら終わりの無い区間。"""

    @abstractmethod
    def list_first_days(self, user_id: int) -> set[date]:
        """確定済みの期間の初日。"""

    @abstractmethod
    def save(self, period: ClosingPeriod) -> ClosingPeriod:
        """同じ期間が既に確定していれば ``ConflictError``（同時に 2 回確定したときなど）。"""

    @abstractmethod
    def delete(self, period_id: int) -> None: ...
