from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.inbox_item import InboxItem


class InboxRepository(ABC):
    @abstractmethod
    def find_by_id(self, item_id: int) -> InboxItem | None: ...
    @abstractmethod
    def find_all(self, user_id: int) -> list[InboxItem]: ...
    @abstractmethod
    def save(self, item: InboxItem) -> InboxItem: ...
    @abstractmethod
    def soft_delete(self, item_id: int) -> None: ...
