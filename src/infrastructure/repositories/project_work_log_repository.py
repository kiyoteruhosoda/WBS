from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.project_work_log import ProjectWorkLog
from src.domain.repositories.project_work_log_repository import ProjectWorkLogRepository
from src.infrastructure.database.models import ProjectWorkLogModel
from src.infrastructure.repositories.project_visibility import visible_project_ids
from src.shared.clock import utcnow


class SqlAlchemyProjectWorkLogRepository(ProjectWorkLogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, log: ProjectWorkLog) -> ProjectWorkLog:
        model = ProjectWorkLogModel(
            user_id=log.user_id,
            project_id=log.project_id,
            work_date=log.work_date,
            duration_seconds=log.seconds,
            tracker_first_day=log.tracker_first_day,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_entity(model)

    def remove_tracker_period(self, user_id: int, first_day: date) -> int:
        stmt = select(ProjectWorkLogModel).where(
            ProjectWorkLogModel.user_id == user_id,
            ProjectWorkLogModel.tracker_first_day == first_day,
            ProjectWorkLogModel.deleted_at.is_(None),
        )
        now = utcnow()
        models = list(self._session.scalars(stmt))
        for model in models:
            model.deleted_at = now
        self._session.flush()
        return len(models)

    def find_for_user(
        self, user_id: int, first_day: date | None = None, last_day: date | None = None
    ) -> list[ProjectWorkLog]:
        stmt = select(ProjectWorkLogModel).where(
            ProjectWorkLogModel.user_id == user_id,
            ProjectWorkLogModel.project_id.in_(visible_project_ids(user_id)),
            ProjectWorkLogModel.deleted_at.is_(None),
        )
        if first_day is not None:
            stmt = stmt.where(ProjectWorkLogModel.work_date >= first_day)
        if last_day is not None:
            stmt = stmt.where(ProjectWorkLogModel.work_date <= last_day)
        stmt = stmt.order_by(
            ProjectWorkLogModel.work_date, ProjectWorkLogModel.project_id, ProjectWorkLogModel.id
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def _to_entity(self, model: ProjectWorkLogModel) -> ProjectWorkLog:
        return ProjectWorkLog(
            id=model.id,
            user_id=model.user_id,
            project_id=model.project_id,
            work_date=model.work_date,
            seconds=model.duration_seconds,
            tracker_first_day=model.tracker_first_day,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
        )


__all__ = ["SqlAlchemyProjectWorkLogRepository"]
