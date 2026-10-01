"""予定の保存先（SQLAlchemy）。ADR-0009。

- 例外と移動は子表（``calendar_event_exceptions`` / ``calendar_event_moves``）。保存のたびに
  集約の今の中身で置き換える。
- 期間で引くときは ``span_start_day`` / ``span_end_day``（``indexed_day_span()``）で粗く絞る。
- 楽観ロック: ``version`` は ORM の ``version_id_col``。UPDATE / DELETE の条件に**読んだときの**
  版が入り、間に別の書き込みがあれば 0 行になって ``ConflictError``。
- ⚠ ``save`` / ``delete`` は flush までで commit しない。確定はユースケースの ``UnitOfWork``。
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from src.application.recurrence_rule_mapping import (
    recurrence_rule_from_mapping,
    recurrence_rule_to_mapping,
)
from src.domain.entities.calendar_event import (
    CalendarEvent,
    EventException,
    EventKind,
    EventMove,
    ExceptionOverride,
    ExceptionType,
)
from src.domain.exceptions import ConflictError
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import (
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.time_zone import TimeZoneId
from src.infrastructure.database.models import (
    CalendarEventExceptionModel,
    CalendarEventModel,
    CalendarEventMoveModel,
)


class SqlAlchemyCalendarEventRepository(CalendarEventRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, event_id: int) -> CalendarEvent | None:
        model = self._session.get(CalendarEventModel, event_id)
        return self._to_entity(model) if model is not None else None

    def find_by_period(self, user_id: int, from_date: date, to_date: date) -> list[CalendarEvent]:
        stmt = (
            select(CalendarEventModel)
            .where(
                CalendarEventModel.user_id == user_id,
                CalendarEventModel.span_start_day <= to_date.toordinal(),
                CalendarEventModel.span_end_day >= from_date.toordinal(),
            )
            .order_by(CalendarEventModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, event: CalendarEvent) -> CalendarEvent:
        if event.id is None:
            model = CalendarEventModel(user_id=event.user_id)
            self._copy_to_model(event, model)
            self._session.add(model)
            self._flush(event)
            event.id = model.id
            return event

        model = self._session.get(CalendarEventModel, event.id)
        if model is None or model.user_id != event.user_id:
            # 読んでから保存するまでの間に消された（または持ち主が違う）。
            raise ConflictError(f"calendar event {event.id} no longer exists")
        # 子表は置き換える。⚠ 同じ回の鍵を消して入れ直すと、ORM は INSERT を DELETE より先に
        #   出すので一意制約に当たる。先に消して flush してから入れる。
        model.exceptions.clear()
        model.moves.clear()
        self._flush(event)
        self._copy_to_model(event, model)
        self._flush(event)
        return event

    def delete(self, event_id: int) -> None:
        model = self._session.get(CalendarEventModel, event_id)
        if model is None:
            return
        self._session.delete(model)
        try:
            self._session.flush()
        except StaleDataError as exc:
            raise ConflictError(f"calendar event {event_id} was changed by someone else") from exc

    # ── 内側 ────────────────────────────────────────────────────────────

    def _flush(self, event: CalendarEvent) -> None:
        try:
            self._session.flush()
        except StaleDataError as exc:
            raise ConflictError(
                f"calendar event {event.id} was changed by someone else"
            ) from exc

    @staticmethod
    def _copy_to_model(event: CalendarEvent, model: CalendarEventModel) -> None:
        span_start, span_end = event.indexed_day_span()
        if event.single_schedule is not None:
            start_utc = event.single_schedule.start_utc
            duration = event.single_schedule.duration_minutes
            rule_text = None
        else:
            assert event.recurring_schedule is not None
            start_utc = event.recurring_schedule.anchor_utc
            duration = event.recurring_schedule.duration_minutes
            rule_text = json.dumps(
                recurrence_rule_to_mapping(event.recurring_schedule.recurrence_rule),
                ensure_ascii=False,
                sort_keys=True,
            )
        model.kind = event.kind.value
        model.title = event.title
        model.time_zone = event.time_zone.name
        model.start_utc = start_utc
        model.duration_minutes = duration
        model.recurrence_rule = rule_text
        model.location = event.location
        model.description = event.description
        model.color_key = event.color_key.value
        model.task_id = event.task_id
        model.span_start_day = span_start
        model.span_end_day = span_end
        model.version = event.version
        model.created_at = event.created_at or event.updated_at
        model.updated_at = event.updated_at or event.created_at
        model.exceptions = [_exception_to_model(e) for e in event.exceptions]
        model.moves = [_move_to_model(m) for m in event.moves]

    @staticmethod
    def _to_entity(model: CalendarEventModel) -> CalendarEvent:
        kind = EventKind(model.kind)
        single = None
        recurring = None
        if kind == EventKind.SINGLE:
            single = SingleEventSchedule(model.start_utc, model.duration_minutes)
        else:
            rule = recurrence_rule_from_mapping(json.loads(model.recurrence_rule or "null") or {})
            recurring = RecurringEventSchedule(model.start_utc, model.duration_minutes, rule)
        return CalendarEvent(
            id=model.id,
            user_id=model.user_id,
            kind=kind,
            title=model.title,
            time_zone=TimeZoneId(model.time_zone),
            single_schedule=single,
            recurring_schedule=recurring,
            location=model.location,
            description=model.description,
            color_key=EventColorKey(model.color_key),
            task_id=model.task_id,
            exceptions=[_exception_to_entity(e) for e in model.exceptions],
            moves=[_move_to_entity(m) for m in model.moves],
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def _exception_to_model(exception: EventException) -> CalendarEventExceptionModel:
    override = exception.override
    return CalendarEventExceptionModel(
        occurrence_date=exception.occurrence_key.date,
        occurrence_time=exception.occurrence_key.time,
        type=exception.type.value,
        override_title=override.title if override else None,
        override_location=override.location if override else None,
        override_start_time=override.start_time if override else None,
        override_duration_minutes=override.duration_minutes if override else None,
    )


def _exception_to_entity(model: CalendarEventExceptionModel) -> EventException:
    override = ExceptionOverride(
        title=model.override_title,
        location=model.override_location,
        start_time=model.override_start_time,
        duration_minutes=model.override_duration_minutes,
    )
    return EventException(
        OccurrenceKey(model.occurrence_date, model.occurrence_time),
        ExceptionType(model.type),
        None if override.is_empty() else override,
    )


def _move_to_model(move: EventMove) -> CalendarEventMoveModel:
    return CalendarEventMoveModel(
        occurrence_date=move.occurrence_key.date,
        occurrence_time=move.occurrence_key.time,
        new_date=move.new_date,
        new_start_time=move.new_start_time,
        new_duration_minutes=move.new_duration_minutes,
        title=move.title,
        location=move.location,
    )


def _move_to_entity(model: CalendarEventMoveModel) -> EventMove:
    return EventMove(
        OccurrenceKey(model.occurrence_date, model.occurrence_time),
        model.new_date,
        model.new_start_time,
        model.new_duration_minutes,
        model.title,
        model.location,
    )


__all__ = ["SqlAlchemyCalendarEventRepository"]
