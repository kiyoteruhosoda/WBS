from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.category import Category


class CategoryRepository(ABC):
    @abstractmethod
    def find_by_id(self, category_id: int) -> Category | None: ...
    @abstractmethod
    def find_all(self, user_id: int) -> list[Category]: ...
    @abstractmethod
    def save(self, category: Category) -> Category: ...
    @abstractmethod
    def soft_delete(self, category_id: int) -> None: ...
