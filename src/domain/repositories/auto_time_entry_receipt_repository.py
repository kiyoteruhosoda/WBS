from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.domain.entities.auto_time_entry_receipt import AutoTimeEntryReceipt


class AutoTimeEntryReceiptRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def find(self, user_id: int, client_ref: str) -> AutoTimeEntryReceipt | None: ...

    @abstractmethod
    def add(self, receipt: AutoTimeEntryReceipt) -> None:
        """同じ ``(user_id, client_ref)`` が既にあれば ``ConflictError``（同時の送り直し）。"""

    @abstractmethod
    def extend(self, user_id: int, client_ref: str, ended_at: datetime) -> None:
        """控えの終わりを ``ended_at`` にする（打刻を伸ばしたあと。ADR-0050）。"""
