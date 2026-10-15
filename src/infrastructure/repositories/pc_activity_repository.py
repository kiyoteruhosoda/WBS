from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.domain.entities.pc_activity import PcActivityDay, PcActivitySpan
from src.domain.repositories.pc_activity_repository import PcActivityRepository
from src.infrastructure.database.models import PcActivityDayModel, PcActivitySpanModel


class SqlAlchemyPcActivityRepository(PcActivityRepository):
    """⚠ 書き込みは flush までで、確定はユースケースの ``UnitOfWork.commit()``。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_day(self, day: PcActivityDay) -> PcActivityDay:
        model = self._session.scalars(
            select(PcActivityDayModel).where(
                PcActivityDayModel.user_id == day.user_id,
                PcActivityDayModel.local_date == day.local_date,
            )
        ).one_or_none()
        if model is None:
            model = PcActivityDayModel(user_id=day.user_id, local_date=day.local_date)
            self._session.add(model)
        else:
            self._session.execute(
                delete(PcActivitySpanModel).where(PcActivitySpanModel.day_id == model.id)
            )
        model.time_zone = day.time_zone
        model.starts_at = day.starts_at
        model.ends_at = day.ends_at
        model.updated_at = day.updated_at
        self._session.flush()
        spans = [
            PcActivitySpanModel(
                day_id=model.id, user_id=day.user_id, started_at=s.started_at, ended_at=s.ended_at
            )
            for s in sorted(day.spans, key=lambda s: s.started_at)
        ]
        self._session.add_all(spans)
        self._session.flush()
        return PcActivityDay(
            id=model.id,
            user_id=model.user_id,
            local_date=model.local_date,
            time_zone=model.time_zone,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
            updated_at=model.updated_at,
            spans=[self._to_span(s) for s in spans],
        )

    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime
    ) -> list[PcActivitySpan]:
        stmt = (
            select(PcActivitySpanModel)
            .where(
                PcActivitySpanModel.user_id == user_id,
                PcActivitySpanModel.started_at < end,
                PcActivitySpanModel.ended_at > start,
            )
            .order_by(PcActivitySpanModel.started_at, PcActivitySpanModel.id)
        )
        return [self._to_span(m) for m in self._session.scalars(stmt)]

    def last_updated_at(self, user_id: int, start: datetime, end: datetime) -> datetime | None:
        return self._session.scalar(
            select(func.max(PcActivityDayModel.updated_at)).where(
                PcActivityDayModel.user_id == user_id,
                PcActivityDayModel.starts_at < end,
                PcActivityDayModel.ends_at > start,
            )
        )

    def delete_days_ended_before(self, user_id: int, cutoff: datetime) -> None:
        old_days = select(PcActivityDayModel.id).where(
            PcActivityDayModel.user_id == user_id, PcActivityDayModel.ends_at <= cutoff
        )
        self._session.execute(
            delete(PcActivitySpanModel).where(PcActivitySpanModel.day_id.in_(old_days))
        )
        self._session.execute(
            delete(PcActivityDayModel).where(
                PcActivityDayModel.user_id == user_id, PcActivityDayModel.ends_at <= cutoff
            )
        )

    def _to_span(self, model: PcActivitySpanModel) -> PcActivitySpan:
        return PcActivitySpan(
            id=model.id, user_id=model.user_id, started_at=model.started_at, ended_at=model.ended_at
        )
