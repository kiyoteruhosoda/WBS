from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.work_log import WorkLog
from src.domain.repositories.work_log_repository import WorkLogRepository
from src.infrastructure.database.models import WorkLogModel
from src.shared.clock import utcnow


class SqlAlchemyWorkLogRepository(WorkLogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, work_log_id: int) -> WorkLog | None:
        model = self._session.get(WorkLogModel, work_log_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    def find_by_task(self, task_id: int) -> list[WorkLog]:
        stmt = select(WorkLogModel).where(
            WorkLogModel.task_id == task_id,
            WorkLogModel.deleted_at.is_(None),
        ).order_by(WorkLogModel.work_date.desc())
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, work_log: WorkLog) -> WorkLog:
        if work_log.id is None:
            model = WorkLogModel(
                user_id=work_log.user_id,
                task_id=work_log.task_id,
                work_date=work_log.work_date,
                hours=work_log.hours,
                memo=work_log.memo,
            )
            self._session.add(model)
            self._session.flush()
            return self._to_entity(model)
        else:
            model = self._session.get(WorkLogModel, work_log.id)
            if model is None:
                raise ValueError(f"WorkLog {work_log.id} not found")
            model.work_date = work_log.work_date
            model.hours = work_log.hours
            model.memo = work_log.memo
            model.updated_at = utcnow()
            self._session.flush()
            return self._to_entity(model)

    def soft_delete(self, work_log_id: int) -> None:
        model = self._session.get(WorkLogModel, work_log_id)
        if model:
            model.deleted_at = utcnow()
            self._session.flush()

    def _to_entity(self, model: WorkLogModel) -> WorkLog:
        return WorkLog(
            id=model.id,
            user_id=model.user_id,
            task_id=model.task_id,
            work_date=model.work_date,
            hours=model.hours,
            memo=model.memo,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
