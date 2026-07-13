from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.category_dto import CreateCategoryDTO, UpdateCategoryDTO
from src.domain.entities.category import Category
from src.domain.exceptions import NotFoundError
from src.infrastructure.repositories.category_repository import SqlAlchemyCategoryRepository


class CategoryUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyCategoryRepository(session)
        self._session = session

    def list_categories(self, user_id: int) -> list[Category]:
        return self._repo.find_all(user_id)

    def get_category(self, category_id: int) -> Category:
        cat = self._repo.find_by_id(category_id)
        if cat is None:
            raise NotFoundError("Category", category_id)
        return cat

    def create_category(self, dto: CreateCategoryDTO) -> Category:
        cat = Category(id=None, user_id=dto.user_id, name=dto.name, color=dto.color, sort_order=dto.sort_order)
        saved = self._repo.save(cat)
        self._session.commit()
        return saved

    def update_category(self, category_id: int, dto: UpdateCategoryDTO) -> Category:
        cat = self._repo.find_by_id(category_id)
        if cat is None:
            raise NotFoundError("Category", category_id)
        if dto.name is not None:
            cat.name = dto.name
        if dto.color is not None:
            cat.color = dto.color
        if dto.sort_order is not None:
            cat.sort_order = dto.sort_order
        saved = self._repo.save(cat)
        self._session.commit()
        return saved

    def delete_category(self, category_id: int) -> None:
        cat = self._repo.find_by_id(category_id)
        if cat is None:
            raise NotFoundError("Category", category_id)
        self._repo.soft_delete(category_id)
        self._session.commit()
