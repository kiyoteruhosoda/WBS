from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.domain.entities.category import Category
from src.domain.repositories.category_repository import CategoryRepository
from src.infrastructure.database.models import CategoryModel


class SqlAlchemyCategoryRepository(CategoryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, category_id: int) -> Category | None:
        model = self._session.get(CategoryModel, category_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    def find_all(self, user_id: int) -> list[Category]:
        stmt = select(CategoryModel).where(
            CategoryModel.user_id == user_id,
            CategoryModel.deleted_at.is_(None),
        ).order_by(CategoryModel.sort_order, CategoryModel.id)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, category: Category) -> Category:
        if category.id is None:
            model = CategoryModel(
                user_id=category.user_id,
                name=category.name,
                color=category.color,
                sort_order=category.sort_order,
            )
            self._session.add(model)
            self._session.flush()
            return self._to_entity(model)
        else:
            model = self._session.get(CategoryModel, category.id)
            if model is None:
                raise ValueError(f"Category {category.id} not found")
            model.name = category.name
            model.color = category.color
            model.sort_order = category.sort_order
            model.updated_at = datetime.utcnow()
            self._session.flush()
            return self._to_entity(model)

    def soft_delete(self, category_id: int) -> None:
        model = self._session.get(CategoryModel, category_id)
        if model:
            model.deleted_at = datetime.utcnow()
            self._session.flush()

    def _to_entity(self, model: CategoryModel) -> Category:
        return Category(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            color=model.color,
            sort_order=model.sort_order,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
