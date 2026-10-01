from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.work_log import WorkLog
from src.domain.repositories.work_log_repository import WorkLogRepository
from src.domain.value_objects.work_log_source import WorkLogSource
from src.infrastructure.database.models import TaskModel, WorkLogModel
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
                source=work_log.source.value,
                closing_period_id=work_log.closing_period_id,
                duration_seconds=work_log.duration_seconds,
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

    def find_by_closing_period(self, closing_period_id: int) -> list[WorkLog]:
        stmt = (
            select(WorkLogModel)
            .where(
                WorkLogModel.closing_period_id == closing_period_id,
                WorkLogModel.deleted_at.is_(None),
            )
            .order_by(WorkLogModel.work_date, WorkLogModel.task_id, WorkLogModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def delete_by_closing_period(self, closing_period_id: int) -> int:
        result = self._session.execute(
            delete(WorkLogModel).where(WorkLogModel.closing_period_id == closing_period_id)
        )
        self._session.flush()
        return result.rowcount or 0

    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[WorkLog]:
        stmt = (
            select(WorkLogModel)
            .join(TaskModel, TaskModel.id == WorkLogModel.task_id)
            .where(
                WorkLogModel.user_id == user_id,
                TaskModel.user_id == user_id,
                WorkLogModel.deleted_at.is_(None),
            )
        )
        if first_day is not None:
            stmt = stmt.where(WorkLogModel.work_date >= first_day)
        if last_day is not None:
            stmt = stmt.where(WorkLogModel.work_date <= last_day)
        stmt = stmt.order_by(WorkLogModel.work_date, WorkLogModel.task_id, WorkLogModel.id)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

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
            source=WorkLogSource(model.source),
            closing_period_id=model.closing_period_id,
            duration_seconds=model.duration_seconds,
        )
