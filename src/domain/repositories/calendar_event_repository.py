from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.entities.calendar_event import CalendarEvent


class CalendarEventRepository(ABC):
    """予定の保存先。⚠ 利用者（``user_id``）で分ける。"""

    @abstractmethod
    def find_by_id(self, event_id: int) -> CalendarEvent | None: ...

    @abstractmethod
    def find_by_period(self, user_id: int, from_date: date, to_date: date) -> list[CalendarEvent]:
        """``[from_date, to_date]``（ローカル日、両端を含む）に回がありうる予定。

        粗い絞り込みでよい（``CalendarEvent.overlaps_period`` と同じ条件。表では
        ``indexed_day_span`` を入れた列で引く）。呼び出し側が展開して正確に絞る。
        """

    @abstractmethod
    def save(self, event: CalendarEvent) -> CalendarEvent:
        """新規（``id is None``）なら採番して返す。"""

    @abstractmethod
    def delete(self, event_id: int) -> None: ...

    @abstractmethod
    def reassign_calendar(self, user_id: int, from_calendar_id: int, to_calendar_id: int) -> int:
        """その利用者の ``from_calendar_id`` の予定を ``to_calendar_id`` へ移す（版を 1 つ進める）。

        カレンダーを消すときに使う（ADR-0027）。移した件数を返す。
        """
