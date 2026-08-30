from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.category_dto import CreateCategoryDTO, UpdateCategoryDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.ownership import owned_by
from src.domain.entities.category import Category
from src.infrastructure.repositories.category_repository import SqlAlchemyCategoryRepository


class CategoryUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyCategoryRepository(session)
        self._session = session

    def list_categories(self, user_id: int) -> list[Category]:
        return self._repo.find_all(user_id)

    def get_category(self, category_id: int, user_id: int) -> Category:
        return self._owned(category_id, user_id)

    def create_category(self, dto: CreateCategoryDTO) -> Category:
        cat = Category(id=None, user_id=dto.user_id, name=dto.name, color=dto.color, sort_order=dto.sort_order)
        saved = self._repo.save(cat)
        self._session.commit()
        return saved

    def update_category(self, category_id: int, user_id: int, dto: UpdateCategoryDTO) -> Category:
        cat = self._owned(category_id, user_id)
        if dto.name is not UNSET:
            cat.name = dto.name
        if dto.color is not UNSET:
            cat.color = dto.color
        if dto.sort_order is not UNSET:
            cat.sort_order = dto.sort_order
        saved = self._repo.save(cat)
        self._session.commit()
        return saved

    def delete_category(self, category_id: int, user_id: int) -> None:
        self._owned(category_id, user_id)
        self._repo.soft_delete(category_id)
        self._session.commit()

    def _owned(self, category_id: int, user_id: int) -> Category:
        return owned_by(
            self._repo.find_by_id(category_id), user_id,
            resource="Category", resource_id=category_id,
        )
