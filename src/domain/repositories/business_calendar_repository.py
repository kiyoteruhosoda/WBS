from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.business_calendar import BusinessCalendar


class BusinessCalendarRepository(ABC):
    """営業日カレンダーの保存先。⚠ 利用者（``user_id``）で分ける。"""

    @abstractmethod
    def find_by_id(self, calendar_id: int) -> BusinessCalendar | None: ...

    @abstractmethod
    def find_all(self, user_id: int) -> list[BusinessCalendar]: ...

    @abstractmethod
    def save(self, calendar: BusinessCalendar) -> BusinessCalendar:
        """新規（``id is None``）なら採番して返す。"""

    @abstractmethod
    def delete(self, calendar_id: int) -> None: ...
