from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.work_break import WorkBreak, WorkBreakSource
from src.domain.repositories.work_break_repository import WorkBreakRepository
from src.infrastructure.database.models import WorkBreakModel


class SqlAlchemyWorkBreakRepository(WorkBreakRepository):
    """⚠ ``replace`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[WorkBreak]:
        stmt = (
            select(WorkBreakModel)
            .where(
                WorkBreakModel.user_id == user_id,
                WorkBreakModel.started_at < end,
                WorkBreakModel.ended_at > start,
            )
            .order_by(WorkBreakModel.started_at, WorkBreakModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def replace(
        self,
        user_id: int,
        source: WorkBreakSource,
        start: datetime,
        end: datetime,
        breaks: list[WorkBreak],
    ) -> list[WorkBreak]:
        self._session.execute(
            delete(WorkBreakModel).where(
                WorkBreakModel.user_id == user_id,
                WorkBreakModel.source == source.value,
                WorkBreakModel.started_at >= start,
                WorkBreakModel.started_at < end,
            )
        )
        models = [
            WorkBreakModel(
                user_id=user_id, started_at=b.started_at, ended_at=b.ended_at, source=source.value
            )
            for b in breaks
        ]
        self._session.add_all(models)
        self._session.flush()
        return [self._to_entity(m) for m in sorted(models, key=lambda m: m.started_at)]

    def _to_entity(self, model: WorkBreakModel) -> WorkBreak:
        return WorkBreak(
            id=model.id,
            user_id=model.user_id,
            started_at=model.started_at,
            ended_at=model.ended_at,
            source=WorkBreakSource(model.source),
            created_at=model.created_at,
        )
