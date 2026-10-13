from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.domain.entities.tracking_rule import TrackingRule
from src.domain.repositories.tracking_rule_repository import TrackingRuleRepository
from src.infrastructure.database.models import (
    TaskModel,
    TrackingRuleBookModel,
    TrackingRuleModel,
)
from src.shared.clock import utcnow


class SqlAlchemyTrackingRuleRepository(TrackingRuleRepository):
    """⚠ ``save`` / ``delete`` / ``mark_changed`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, rule_id: int) -> TrackingRule | None:
        model = self._session.get(TrackingRuleModel, rule_id)
        return self._to_entity(model) if model is not None else None

    def find_all(self, user_id: int) -> list[TrackingRule]:
        stmt = (
            select(TrackingRuleModel)
            .where(TrackingRuleModel.user_id == user_id)
            .order_by(TrackingRuleModel.position, TrackingRuleModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, rule: TrackingRule) -> TrackingRule:
        if rule.id is None:
            model = TrackingRuleModel(
                user_id=rule.user_id,
                position=rule.position,
                app=rule.app,
                title_contains=rule.title_contains,
                task_id=rule.task_id,
            )
            self._session.add(model)
        else:
            found = self._session.get(TrackingRuleModel, rule.id)
            if found is None:
                raise ValueError(f"TrackingRule {rule.id} not found")
            model = found
            model.position = rule.position
            model.app = rule.app
            model.title_contains = rule.title_contains
            model.task_id = rule.task_id
            model.updated_at = utcnow()
        self._session.flush()
        return self._to_entity(model)

    def delete(self, rule_id: int) -> None:
        model = self._session.get(TrackingRuleModel, rule_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    def last_changed_at(self, user_id: int) -> datetime | None:
        book = self._session.get(TrackingRuleBookModel, user_id)
        return book.changed_at if book is not None else None

    def mark_changed(self, user_id: int, at: datetime) -> None:
        book = self._session.get(TrackingRuleBookModel, user_id)
        if book is None:
            self._session.add(TrackingRuleBookModel(user_id=user_id, changed_at=at))
        else:
            book.changed_at = at
        self._session.flush()

    def last_task_change_at(self, user_id: int) -> datetime | None:
        # 消したタスクも数える（deleted_at の付いた行も読む）。updated_at が進まない消し方にも備えて deleted_at も見る
        stmt = (
            select(
                func.max(TaskModel.updated_at),
                func.max(TaskModel.deleted_at),
            )
            .join(TrackingRuleModel, TrackingRuleModel.task_id == TaskModel.id)
            .where(TrackingRuleModel.user_id == user_id)
        )
        updated, deleted = self._session.execute(stmt).one()
        stamps = [s for s in (updated, deleted) if s is not None]
        return max(stamps) if stamps else None

    def _to_entity(self, model: TrackingRuleModel) -> TrackingRule:
        return TrackingRule(
            id=model.id,
            user_id=model.user_id,
            position=model.position,
            task_id=model.task_id,
            app=model.app,
            title_contains=model.title_contains,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
