from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.auto_time_entry_receipt import AutoTimeEntryReceipt


class AutoTimeEntryReceiptRepository(ABC):
    """⚠ 確定（commit）はしない。確定はユースケースの ``UnitOfWork.commit()``。"""

    @abstractmethod
    def find(self, user_id: int, client_ref: str) -> AutoTimeEntryReceipt | None: ...

    @abstractmethod
    def add(self, receipt: AutoTimeEntryReceipt) -> None:
        """同じ ``(user_id, client_ref)`` が既にあれば ``ConflictError``（同時の送り直し）。"""
