from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.domain.entities.inbox_item import InboxItem
from src.domain.repositories.inbox_repository import InboxRepository
from src.infrastructure.database.models import InboxItemModel


class SqlAlchemyInboxRepository(InboxRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, item_id: int) -> InboxItem | None:
        model = self._session.get(InboxItemModel, item_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    def find_all(self, user_id: int) -> list[InboxItem]:
        stmt = select(InboxItemModel).where(
            InboxItemModel.user_id == user_id,
            InboxItemModel.deleted_at.is_(None),
            InboxItemModel.converted_at.is_(None),
        ).order_by(InboxItemModel.id.desc())
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, item: InboxItem) -> InboxItem:
        if item.id is None:
            model = InboxItemModel(
                user_id=item.user_id,
                title=item.title,
                memo=item.memo,
                converted_task_id=item.converted_task_id,
                converted_at=item.converted_at,
            )
            self._session.add(model)
            self._session.flush()
            return self._to_entity(model)
        else:
            model = self._session.get(InboxItemModel, item.id)
            if model is None:
                raise ValueError(f"InboxItem {item.id} not found")
            model.title = item.title
            model.memo = item.memo
            model.converted_task_id = item.converted_task_id
            model.converted_at = item.converted_at
            model.updated_at = datetime.utcnow()
            self._session.flush()
            return self._to_entity(model)

    def soft_delete(self, item_id: int) -> None:
        model = self._session.get(InboxItemModel, item_id)
        if model:
            model.deleted_at = datetime.utcnow()
            self._session.flush()

    def _to_entity(self, model: InboxItemModel) -> InboxItem:
        return InboxItem(
            id=model.id,
            user_id=model.user_id,
            title=model.title,
            memo=model.memo,
            converted_task_id=model.converted_task_id,
            converted_at=model.converted_at,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
