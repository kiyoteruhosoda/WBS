"""営業日カレンダーの保存先（SQLAlchemy）。ADR-0009。

祝日は子表（``business_calendar_holidays``）で、保存のたびに集約の今の中身で置き換える。
⚠ ``save`` / ``delete`` は flush までで commit しない（確定はユースケースの ``UnitOfWork``）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.exceptions import ConflictError
from src.domain.repositories.business_calendar_repository import BusinessCalendarRepository
from src.domain.value_objects.recurrence import Weekday
from src.domain.value_objects.time_zone import TimeZoneId
from src.infrastructure.database.models import (
    BusinessCalendarHolidayModel,
    BusinessCalendarModel,
)

_WORKDAY_SEPARATOR = ","


class SqlAlchemyBusinessCalendarRepository(BusinessCalendarRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, calendar_id: int) -> BusinessCalendar | None:
        model = self._session.get(BusinessCalendarModel, calendar_id)
        return _to_entity(model) if model is not None else None

    def find_all(self, user_id: int) -> list[BusinessCalendar]:
        stmt = (
            select(BusinessCalendarModel)
            .where(BusinessCalendarModel.user_id == user_id)
            .order_by(BusinessCalendarModel.id)
        )
        return [_to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, calendar: BusinessCalendar) -> BusinessCalendar:
        if calendar.id is None:
            model = BusinessCalendarModel(user_id=calendar.user_id)
            _copy_to_model(calendar, model)
            self._session.add(model)
            self._session.flush()
            calendar.id = model.id
            return calendar

        model = self._session.get(BusinessCalendarModel, calendar.id)
        if model is None or model.user_id != calendar.user_id:
            raise ConflictError(f"business calendar {calendar.id} no longer exists")
        # 同じ日を消して入れ直すと INSERT が DELETE より先に出て一意制約に当たるので、先に消す。
        model.holidays.clear()
        self._session.flush()
        _copy_to_model(calendar, model)
        self._session.flush()
        return calendar

    def delete(self, calendar_id: int) -> None:
        model = self._session.get(BusinessCalendarModel, calendar_id)
        if model is None:
            return
        self._session.delete(model)
        self._session.flush()


def _copy_to_model(calendar: BusinessCalendar, model: BusinessCalendarModel) -> None:
    model.name = calendar.name
    model.time_zone = calendar.time_zone.name
    model.workdays = _WORKDAY_SEPARATOR.join(
        w.value for w in sorted(calendar.workdays, key=lambda w: w.iso_index)
    )
    model.shift_on_holidays_only = calendar.shift_on_holidays_only
    model.is_enabled = calendar.is_enabled
    model.created_at = calendar.created_at or calendar.updated_at
    model.updated_at = calendar.updated_at or calendar.created_at
    model.holidays = [
        BusinessCalendarHolidayModel(holiday_date=h.date, name=h.name)
        for h in sorted(calendar.holidays, key=lambda h: h.date)
    ]


def _to_entity(model: BusinessCalendarModel) -> BusinessCalendar:
    workdays = frozenset(
        Weekday(code) for code in model.workdays.split(_WORKDAY_SEPARATOR) if code
    )
    return BusinessCalendar(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        time_zone=TimeZoneId(model.time_zone),
        workdays=workdays,
        holidays=[Holiday(h.holiday_date, h.name) for h in model.holidays],
        shift_on_holidays_only=model.shift_on_holidays_only,
        is_enabled=model.is_enabled,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


__all__ = ["SqlAlchemyBusinessCalendarRepository"]
