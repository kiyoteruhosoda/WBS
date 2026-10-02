from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.calendar import Calendar
from src.domain.entities.calendar_view_preset import CalendarViewPreset


class CalendarRepository(ABC):
    """予定のカレンダーの保存先（ADR-0027）。⚠ 利用者（``user_id``）で分ける。

    ⚠ 書き込みは flush までで、確定はユースケースの ``UnitOfWork.commit()``。
    """

    @abstractmethod
    def find_by_id(self, calendar_id: int) -> Calendar | None: ...

    @abstractmethod
    def find_all(self, user_id: int) -> list[Calendar]:
        """並び順（``sort_order``、同じなら id）で。"""

    @abstractmethod
    def save(self, calendar: Calendar) -> Calendar:
        """新規（``id is None``）なら採番して返す。"""

    @abstractmethod
    def delete(self, calendar_id: int) -> None: ...


class CalendarViewPresetRepository(ABC):
    """表示の組み合わせの保存先（ADR-0027）。⚠ 利用者（``user_id``）で分ける。"""

    @abstractmethod
    def find_by_id(self, preset_id: int) -> CalendarViewPreset | None: ...

    @abstractmethod
    def find_all(self, user_id: int) -> list[CalendarViewPreset]:
        """並び順（``sort_order``、同じなら id）で。"""

    @abstractmethod
    def save(self, preset: CalendarViewPreset) -> CalendarViewPreset: ...

    @abstractmethod
    def delete(self, preset_id: int) -> None: ...
