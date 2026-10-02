"""予定の保存先（SQLAlchemy）。ADR-0009。

- 例外と移動は子表（``calendar_event_exceptions`` / ``calendar_event_moves``）。保存のたびに
  集約の今の中身で置き換える。
- 期間で引くときは ``span_start_day`` / ``span_end_day``（``indexed_day_span()``）で粗く絞る。
- 楽観ロック: 書く前に ``UPDATE ... SET version = <新しい版> WHERE id = ? AND version = <読んだ版>``
  を出し、1 行に当たらなければ（間に別の書き込みがあった）``ConflictError``。当たれば行の鍵を
  握ったまま残りを書く。消すときも同じ確かめをしてから消す。「読んだ版」はこのリポジトリが
  読んだときに覚えておく（⚠ ORM の identity map は弱参照なので、行の写しは読み直されうる）。
- ⚠ ``save`` / ``delete`` は flush までで commit しない。確定はユースケースの ``UnitOfWork``。
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.application.recurrence_rule_mapping import (
    recurrence_rule_from_mapping,
    recurrence_rule_to_mapping,
)
from src.domain.entities.calendar_event import (
    CalendarEvent,
    EventException,
    EventKind,
    EventMove,
    EventType,
    ExceptionOverride,
    ExceptionType,
)
from src.domain.exceptions import ConflictError
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.services.default_calendar import ensure_default_calendar
from src.domain.value_objects.event_alarm import EventAlarm
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
from src.infrastructure.repositories.calendar_repository import SqlAlchemyCalendarRepository
from src.shared.clock import utcnow


class SqlAlchemyCalendarEventRepository(CalendarEventRepository):
    def __init__(self, session: Session) -> None:
        self._session = session
        self._read_versions: dict[int, int] = {}
        """予定の id → このリポジトリが読んだ（または書いた）版。"""

    def find_by_id(self, event_id: int) -> CalendarEvent | None:
        model = self._session.get(CalendarEventModel, event_id)
        return self._read(model) if model is not None else None

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
        return [self._read(m) for m in self._session.scalars(stmt)]

    def save(self, event: CalendarEvent) -> CalendarEvent:
        if event.calendar_id is None:
            # カレンダーを決めずに来た予定は、利用者の既定のカレンダーへ（ADR-0027）。
            default = ensure_default_calendar(
                SqlAlchemyCalendarRepository(self._session), event.user_id, utcnow()
            )
            event.calendar_id = default.id
        if event.id is None:
            model = CalendarEventModel(user_id=event.user_id)
            self._copy_to_model(event, model)
            self._session.add(model)
            self._session.flush()
            event.id = model.id
            self._read_versions[model.id] = event.version
            return event

        model = self._session.get(CalendarEventModel, event.id)
        if model is None or model.user_id != event.user_id:
            # 読んでから保存するまでの間に消された（または持ち主が違う）。
            raise ConflictError(f"calendar event {event.id} no longer exists")
        self._claim_version(model.id, event.version)
        # 子表は置き換える。⚠ 同じ回の鍵を消して入れ直すと、ORM は INSERT を DELETE より先に
        #   出すので一意制約に当たる。先に消して flush してから入れる。
        model.exceptions.clear()
        model.moves.clear()
        self._session.flush()
        self._copy_to_model(event, model)
        self._session.flush()
        self._read_versions[model.id] = event.version
        return event

    def delete(self, event_id: int) -> None:
        model = self._session.get(CalendarEventModel, event_id)
        if model is None:
            return
        self._claim_version(event_id, None)
        self._session.delete(model)
        self._session.flush()
        self._read_versions.pop(event_id, None)

    def reassign_calendar(self, user_id: int, from_calendar_id: int, to_calendar_id: int) -> int:
        table = CalendarEventModel.__table__
        result = self._session.execute(
            update(table)
            .where(table.c.user_id == user_id, table.c.calendar_id == from_calendar_id)
            .values(calendar_id=to_calendar_id, version=table.c.version + 1)
        )
        # 読んだ版を覚えていれば、移したものは古い（次の保存は ConflictError で読み直させる）。
        self._session.expire_all()
        return int(result.rowcount or 0)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _read(self, model: CalendarEventModel) -> CalendarEvent:
        self._read_versions[model.id] = model.version
        return self._to_entity(model)

    def _claim_version(self, event_id: int, new_version: int | None) -> None:
        """読んだ版のままなら版を ``new_version``（None は据え置き）にする。違えば ``ConflictError``。

        条件付きの UPDATE が当たった時点で行（SQLite は DB）の書き込みの鍵を握るので、確定までの
        間に割り込まれない。読まずに書こうとしたもの（このリポジトリで読んでいない id）も断る。
        """
        read_version = self._read_versions.get(event_id)
        if read_version is None:
            raise ConflictError(f"calendar event {event_id} must be read before it is written")
        table = CalendarEventModel.__table__
        result = self._session.execute(
            update(table)
            .where(table.c.id == event_id, table.c.version == read_version)
            .values(version=read_version if new_version is None else new_version)
        )
        if result.rowcount != 1:
            raise ConflictError(f"calendar event {event_id} was changed by someone else")

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
        model.event_type = event.event_type.value
        model.calendar_id = event.calendar_id
        alarm = event.alarm
        model.alarm_enabled = alarm.is_enabled if alarm is not None else None
        model.alarm_15_min = alarm.notify_15_min if alarm is not None else False
        model.alarm_5_min = alarm.notify_5_min if alarm is not None else False
        model.alarm_1_min = alarm.notify_1_min if alarm is not None else False
        model.alarm_at_start = alarm.notify_at_start if alarm is not None else False
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
            alarm=_alarm_to_entity(model),
            event_type=EventType(model.event_type),
            calendar_id=model.calendar_id,
            exceptions=[_exception_to_entity(e) for e in model.exceptions],
            moves=[_move_to_entity(m) for m in model.moves],
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


def _alarm_to_entity(model: CalendarEventModel) -> EventAlarm | None:
    if model.alarm_enabled is None:
        return None
    return EventAlarm(
        is_enabled=bool(model.alarm_enabled),
        notify_15_min=bool(model.alarm_15_min),
        notify_5_min=bool(model.alarm_5_min),
        notify_1_min=bool(model.alarm_1_min),
        notify_at_start=bool(model.alarm_at_start),
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
