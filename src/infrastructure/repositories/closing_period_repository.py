from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.closing_period import ClosingPeriod
from src.domain.exceptions import ConflictError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.infrastructure.database.models import ClosingPeriodModel


class SqlAlchemyClosingPeriodRepository(ClosingPeriodRepository):
    """⚠ ``save`` / ``delete`` は flush までで、確定はユースケースの ``UnitOfWork.commit()``。

    確定は期間の行と ``work_logs`` の行を 1 度に書くので、ここで commit すると片方だけ残りうる。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_first_day(self, user_id: int, first_day: date) -> ClosingPeriod | None:
        model = self._session.scalar(
            select(ClosingPeriodModel).where(
                ClosingPeriodModel.user_id == user_id,
                ClosingPeriodModel.first_day == first_day,
            )
        )
        return self._to_entity(model) if model is not None else None

    def find_overlapping(
        self, user_id: int, start: datetime, end: datetime | None
    ) -> list[ClosingPeriod]:
        stmt = select(ClosingPeriodModel).where(
            ClosingPeriodModel.user_id == user_id,
            ClosingPeriodModel.ends_at > start,
        )
        if end is not None:
            stmt = stmt.where(ClosingPeriodModel.starts_at < end)
        stmt = stmt.order_by(ClosingPeriodModel.starts_at)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def list_first_days(self, user_id: int) -> set[date]:
        stmt = select(ClosingPeriodModel.first_day).where(ClosingPeriodModel.user_id == user_id)
        return set(self._session.scalars(stmt))

    def save(self, period: ClosingPeriod) -> ClosingPeriod:
        if period.id is not None:
            raise ValueError("A closing period is closed once; reopen deletes it")
        model = ClosingPeriodModel(
            user_id=period.user_id,
            first_day=period.first_day,
            last_day=period.last_day,
            time_zone=period.time_zone,
            starts_at=period.starts_at,
            ends_at=period.ends_at,
            closed_at=period.closed_at,
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            if "uq_closing_periods_user_first_day" not in str(exc.orig) and (
                "closing_periods.user_id" not in str(exc.orig)
            ):
                raise
            raise ConflictError("This closing period is already closed") from exc
        return self._to_entity(model)

    def delete(self, period_id: int) -> None:
        model = self._session.get(ClosingPeriodModel, period_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()

    def _to_entity(self, model: ClosingPeriodModel) -> ClosingPeriod:
        return ClosingPeriod(
            id=model.id,
            user_id=model.user_id,
            first_day=model.first_day,
            last_day=model.last_day,
            time_zone=model.time_zone,
            starts_at=model.starts_at,
            ends_at=model.ends_at,
            closed_at=model.closed_at,
        )
