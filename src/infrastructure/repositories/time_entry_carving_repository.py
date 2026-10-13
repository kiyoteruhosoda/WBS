from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.time_entry_carving import CarvingAction, TimeEntryCarving
from src.domain.repositories.time_entry_carving_repository import TimeEntryCarvingRepository
from src.infrastructure.database.models import TimeEntryCarvingModel


class SqlAlchemyTimeEntryCarvingRepository(TimeEntryCarvingRepository):
    """⚠ ``add`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, carving: TimeEntryCarving) -> TimeEntryCarving:
        model = TimeEntryCarvingModel(
            user_id=carving.user_id,
            client_ref=carving.client_ref,
            time_entry_id=carving.time_entry_id,
            action=carving.action.value,
            task_id=carving.task_id,
            source=carving.source,
            memo=carving.memo,
            started_at=carving.started_at,
            ended_at=carving.ended_at,
            window_started_at=carving.window_started_at,
            window_ended_at=carving.window_ended_at,
            carved_at=carving.carved_at,
        )
        self._session.add(model)
        self._session.flush()
        return self._to_entity(model)

    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[TimeEntryCarving]:
        stmt = (
            select(TimeEntryCarvingModel)
            .where(
                TimeEntryCarvingModel.user_id == user_id,
                TimeEntryCarvingModel.window_started_at < end,
                TimeEntryCarvingModel.window_ended_at > start,
            )
            .order_by(TimeEntryCarvingModel.carved_at, TimeEntryCarvingModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def _to_entity(self, model: TimeEntryCarvingModel) -> TimeEntryCarving:
        return TimeEntryCarving(
            id=model.id,
            user_id=model.user_id,
            client_ref=model.client_ref,
            time_entry_id=model.time_entry_id,
            action=CarvingAction(model.action),
            task_id=model.task_id,
            source=model.source,
            memo=model.memo,
            started_at=model.started_at,
            ended_at=model.ended_at,
            window_started_at=model.window_started_at,
            window_ended_at=model.window_ended_at,
            carved_at=model.carved_at,
        )
