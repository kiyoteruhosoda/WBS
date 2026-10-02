from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from datetime import date, datetime

from src.domain.entities.calendar_import import CalendarImport
from src.domain.value_objects.imported_occurrence import ImportedOccurrence


class CalendarImportRepository(ABC):
    """取り込んだカレンダーの読み込みの状態（ADR-0037）。持ち主はカレンダーで決まる（呼び出し側が確かめる）。

    ⚠ 書き込みは flush までで、確定はユースケースの ``UnitOfWork.commit()``。
    """

    @abstractmethod
    def find(self, calendar_id: int) -> CalendarImport | None: ...

    @abstractmethod
    def find_many(self, calendar_ids: Iterable[int]) -> list[CalendarImport]: ...

    @abstractmethod
    def find_subscribed(self) -> list[CalendarImport]:
        """URL を購読しているもの全部（定期の読み込みが使う。利用者をまたぐ）。"""

    @abstractmethod
    def save(self, calendar_import: CalendarImport) -> CalendarImport: ...

    @abstractmethod
    def delete(self, calendar_id: int) -> None: ...


class ImportedOccurrenceRepository(ABC):
    """取り込んだカレンダーの回（ADR-0037）。持ち主はカレンダーで決まる（呼び出し側が確かめる）。

    ⚠ 書き込みは flush までで、確定はユースケースの ``UnitOfWork.commit()``。
    """

    @abstractmethod
    def replace(self, calendar_id: int, occurrences: Sequence[ImportedOccurrence]) -> None:
        """そのカレンダーの回を丸ごと入れ替える。"""

    @abstractmethod
    def find(
        self,
        calendar_ids: Iterable[int],
        *,
        from_utc: datetime,
        to_utc: datetime,
        from_date: date,
        to_date: date,
    ) -> list[tuple[int, ImportedOccurrence]]:
        """``(calendar_id, 回)`` の組。時刻のある回は ``[from_utc, to_utc)`` に掛かるもの、終日の回は
        ``[from_date, to_date]`` の日に掛かるもの。"""

    @abstractmethod
    def delete_all(self, calendar_id: int) -> None: ...
