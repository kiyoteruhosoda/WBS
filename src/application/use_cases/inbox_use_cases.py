from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.inbox_dto import ConvertInboxItemDTO, CreateInboxItemDTO
from src.domain.entities.inbox_item import InboxItem
from src.domain.exceptions import NotFoundError
from src.infrastructure.repositories.inbox_repository import SqlAlchemyInboxRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.shared.clock import utcnow


class InboxUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyInboxRepository(session)
        self._task_repo = SqlAlchemyTaskRepository(session)
        self._session = session

    def list_items(self, user_id: int) -> list[InboxItem]:
        return self._repo.find_all(user_id)

    def get_item(self, item_id: int) -> InboxItem:
        item = self._repo.find_by_id(item_id)
        if item is None:
            raise NotFoundError("InboxItem", item_id)
        return item

    def create_item(self, dto: CreateInboxItemDTO) -> InboxItem:
        item = InboxItem(id=None, user_id=dto.user_id, title=dto.title, memo=dto.memo)
        saved = self._repo.save(item)
        self._session.commit()
        return saved

    def delete_item(self, item_id: int) -> None:
        item = self._repo.find_by_id(item_id)
        if item is None:
            raise NotFoundError("InboxItem", item_id)
        self._repo.soft_delete(item_id)
        self._session.commit()

    def convert_to_task(self, item_id: int, dto: ConvertInboxItemDTO) -> dict:
        item = self._repo.find_by_id(item_id)
        if item is None:
            raise NotFoundError("InboxItem", item_id)
        from src.domain.entities.task import Task
        task = Task(
            id=None,
            user_id=item.user_id,
            title=dto.title or item.title,
            category_id=dto.category_id,
            priority=dto.priority,
            urgency=dto.urgency,
            start_date=dto.start_date,
            due_date=dto.due_date,
            estimated_hours=dto.estimated_hours,
            memo=dto.memo or item.memo,
        )
        saved_task = self._task_repo.save(task)
        item.converted_task_id = saved_task.id
        item.converted_at = utcnow()
        self._repo.save(item)
        self._session.commit()
        from src.application.use_cases.task_use_cases import TaskUseCases
        uc = TaskUseCases(self._session)
        return uc._enrich(saved_task)
