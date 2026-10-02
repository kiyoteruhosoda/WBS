"""予定のカレンダーと表示の組み合わせの保存先（SQLAlchemy）。ADR-0027。

⚠ ``save`` / ``delete`` は flush までで commit しない（確定はユースケースの ``UnitOfWork``）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.calendar import Calendar, CalendarKind, DayOffReason
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.entities.day_off import DayOff
from src.domain.exceptions import ConflictError
from src.domain.repositories.calendar_repository import (
    CalendarRepository,
    CalendarViewPresetRepository,
    DayOffRepository,
)
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.recurrence import Weekday
from src.infrastructure.database.models import (
    CalendarDayOffModel,
    CalendarModel,
    CalendarViewPresetModel,
)

_WORKDAY_SEPARATOR = ","


class SqlAlchemyCalendarRepository(CalendarRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, calendar_id: int) -> Calendar | None:
        model = self._session.get(CalendarModel, calendar_id)
        return _calendar(model) if model is not None else None

    def find_all(self, user_id: int) -> list[Calendar]:
        stmt = (
            select(CalendarModel)
            .where(CalendarModel.user_id == user_id)
            .order_by(CalendarModel.sort_order, CalendarModel.id)
        )
        return [_calendar(m) for m in self._session.scalars(stmt)]

    def save(self, calendar: Calendar) -> Calendar:
        if calendar.id is None:
            model = CalendarModel(user_id=calendar.user_id)
            _copy_calendar(calendar, model)
            self._session.add(model)
            self._session.flush()
            calendar.id = model.id
            return calendar
        model = self._session.get(CalendarModel, calendar.id)
        if model is None or model.user_id != calendar.user_id:
            raise ConflictError(f"calendar {calendar.id} no longer exists")
        _copy_calendar(calendar, model)
        self._session.flush()
        return calendar

    def delete(self, calendar_id: int) -> None:
        model = self._session.get(CalendarModel, calendar_id)
        if model is None:
            return
        self._session.delete(model)
        self._session.flush()


class SqlAlchemyCalendarViewPresetRepository(CalendarViewPresetRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, preset_id: int) -> CalendarViewPreset | None:
        model = self._session.get(CalendarViewPresetModel, preset_id)
        return _preset(model) if model is not None else None

    def find_all(self, user_id: int) -> list[CalendarViewPreset]:
        stmt = (
            select(CalendarViewPresetModel)
            .where(CalendarViewPresetModel.user_id == user_id)
            .order_by(CalendarViewPresetModel.sort_order, CalendarViewPresetModel.id)
        )
        return [_preset(m) for m in self._session.scalars(stmt)]

    def save(self, preset: CalendarViewPreset) -> CalendarViewPreset:
        if preset.id is None:
            model = CalendarViewPresetModel(user_id=preset.user_id)
            _copy_preset(preset, model)
            self._session.add(model)
            self._session.flush()
            preset.id = model.id
            return preset
        model = self._session.get(CalendarViewPresetModel, preset.id)
        if model is None or model.user_id != preset.user_id:
            raise ConflictError(f"view preset {preset.id} no longer exists")
        _copy_preset(preset, model)
        self._session.flush()
        return preset

    def delete(self, preset_id: int) -> None:
        model = self._session.get(CalendarViewPresetModel, preset_id)
        if model is None:
            return
        self._session.delete(model)
        self._session.flush()


class SqlAlchemyDayOffRepository(DayOffRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(
        self, calendar_ids: Iterable[int], from_date: date | None = None, to_date: date | None = None
    ) -> list[DayOff]:
        ids = list(calendar_ids)
        if not ids:
            return []
        stmt = select(CalendarDayOffModel).where(CalendarDayOffModel.calendar_id.in_(ids))
        if from_date is not None:
            stmt = stmt.where(CalendarDayOffModel.day >= from_date)
        if to_date is not None:
            stmt = stmt.where(CalendarDayOffModel.day <= to_date)
        stmt = stmt.order_by(CalendarDayOffModel.day, CalendarDayOffModel.calendar_id)
        return [DayOff(m.calendar_id, m.day, m.name) for m in self._session.scalars(stmt)]

    def add(self, day_off: DayOff) -> bool:
        exists = self._session.scalar(
            select(CalendarDayOffModel.id).where(
                CalendarDayOffModel.calendar_id == day_off.calendar_id,
                CalendarDayOffModel.day == day_off.day,
            )
        )
        if exists is not None:
            return False
        self._session.add(
            CalendarDayOffModel(calendar_id=day_off.calendar_id, day=day_off.day, name=day_off.name)
        )
        self._session.flush()
        return True

    def remove(self, calendar_id: int, day: date) -> bool:
        result = self._session.execute(
            delete(CalendarDayOffModel).where(
                CalendarDayOffModel.calendar_id == calendar_id, CalendarDayOffModel.day == day
            )
        )
        return bool(result.rowcount)


def _copy_calendar(calendar: Calendar, model: CalendarModel) -> None:
    model.kind = calendar.kind.value
    model.name = calendar.name
    model.color_key = calendar.color_key.value
    model.sort_order = calendar.sort_order
    model.is_default = calendar.is_default
    model.is_visible = calendar.is_visible
    model.workdays = (
        _WORKDAY_SEPARATOR.join(w.value for w in sorted(calendar.workdays, key=lambda w: w.iso_index))
        if calendar.workdays is not None
        else None
    )
    model.day_off_reason = calendar.day_off_reason.value if calendar.day_off_reason else None
    model.counts_as_day_off = calendar.counts_as_day_off
    model.created_at = calendar.created_at or calendar.updated_at
    model.updated_at = calendar.updated_at or calendar.created_at


def _calendar(model: CalendarModel) -> Calendar:
    return Calendar(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        color_key=EventColorKey(model.color_key),
        sort_order=model.sort_order,
        is_default=model.is_default,
        is_visible=model.is_visible,
        kind=CalendarKind(model.kind),
        workdays=(
            frozenset(Weekday(code) for code in model.workdays.split(_WORKDAY_SEPARATOR) if code)
            if model.workdays is not None
            else None
        ),
        day_off_reason=DayOffReason(model.day_off_reason) if model.day_off_reason else None,
        counts_as_day_off=bool(model.counts_as_day_off),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _copy_preset(preset: CalendarViewPreset, model: CalendarViewPresetModel) -> None:
    model.name = preset.name
    model.calendar_ids = json.dumps(list(preset.calendar_ids))
    model.sort_order = preset.sort_order
    model.created_at = preset.created_at or preset.updated_at
    model.updated_at = preset.updated_at or preset.created_at


def _preset(model: CalendarViewPresetModel) -> CalendarViewPreset:
    ids = json.loads(model.calendar_ids or "[]")
    return CalendarViewPreset(
        id=model.id,
        user_id=model.user_id,
        name=model.name,
        calendar_ids=tuple(int(i) for i in ids),
        sort_order=model.sort_order,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


__all__ = [
    "SqlAlchemyCalendarRepository",
    "SqlAlchemyCalendarViewPresetRepository",
    "SqlAlchemyDayOffRepository",
]
