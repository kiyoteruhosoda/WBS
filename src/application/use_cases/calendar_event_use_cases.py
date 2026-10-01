"""予定のユースケース（移植元 ``CalendarEventApplicationService``）。

- 期間で引く: ``find_by_period``（予定）・``list_occurrences``（展開した回）
- 作る・直す: 単発／繰り返し、すべて・この回以降・この回だけ
- 回の操作: 飛ばす・飛ばすの取り消し・移動・移動の取り消し
- 消す: 予定ごと・この回以降

どの操作も ``user_id`` で持ち主を確かめる（他人の予定は「無い」として扱う）。
時刻は UTC の瞬間 ＋ 長さ（分）で受け取り、作成・更新の時刻は ``now``
（既定は ``src.shared.clock.utcnow``）で付ける。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from src.application.dto.calendar_event_dto import (
    ChangeFollowingOccurrencesCommand,
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    MoveOccurrenceCommand,
    OccurrenceCommand,
    RescheduleSingleEventCommand,
    SplitThisOccurrenceCommand,
    UpdateEventCommand,
    UpdateRecurringSeriesCommand,
)
from src.application.dto.unset import UNSET
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.business_calendar import BusinessCalendar
from src.domain.entities.calendar_event import CalendarEvent
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.repositories.business_calendar_repository import BusinessCalendarRepository
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.services.occurrence_display_projection import to_display_time_zone
from src.domain.services.occurrence_expander import OccurrenceExpander
from src.domain.value_objects.event_schedule import (
    EventOccurrence,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.local_schedule_point import local_date_of, local_time_of
from src.domain.value_objects.recurrence import RecurrenceRule
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow


def _shift_clamped(day: date, days: int) -> date:
    try:
        return day + timedelta(days=days)
    except OverflowError:
        return date.max if days > 0 else date.min


class CalendarEventUseCases:
    def __init__(
        self,
        events: CalendarEventRepository,
        calendars: BusinessCalendarRepository,
        tasks: OwnedTaskLookup,
        unit_of_work: UnitOfWork,
        *,
        expander: OccurrenceExpander | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._events = events
        self._calendars = calendars
        self._tasks = tasks
        self._uow = unit_of_work
        self._expander = expander or OccurrenceExpander()
        self._now = now

    # ── 引く ────────────────────────────────────────────────────────────

    def get_event(self, event_id: int, user_id: int) -> CalendarEvent:
        return self._owned(event_id, user_id)

    def find_by_period(self, user_id: int, from_date: date, to_date: date) -> list[CalendarEvent]:
        """``[from_date, to_date]`` に回がありうる予定（粗い絞り込み）。"""
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        return self._events.find_by_period(user_id, from_date, to_date)

    def list_occurrences(
        self,
        user_id: int,
        from_date: date,
        to_date: date,
        viewer_time_zone: str | None = None,
    ) -> list[EventOccurrence]:
        """期間の中の回を、日付・開始時刻の順に返す。

        ``viewer_time_zone`` を渡すと、回をそのゾーンへ投影し、閲覧者のローカル日で
        期間に入るものだけを返す。境目の回が投影で隣の日へ移りうるので、展開は前後 1 日
        広げて行う。省くと予定ごとのタイムゾーンの壁時計のまま返す。
        """
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        viewer = TimeZoneId(viewer_time_zone) if viewer_time_zone else None
        pad = 1 if viewer else 0
        expand_from = _shift_clamped(from_date, -pad)
        expand_to = _shift_clamped(to_date, pad)

        calendars: dict[int, BusinessCalendar | None] = {}
        results: list[EventOccurrence] = []
        for event in self._events.find_by_period(user_id, expand_from, expand_to):
            calendar = self._calendar_for(event, calendars)
            for occurrence in self._expander.expand(event, expand_from, expand_to, calendar):
                if viewer is not None:
                    occurrence = to_display_time_zone(occurrence, event.time_zone, viewer)
                    if not from_date <= occurrence.date <= to_date:
                        continue
                results.append(occurrence)
        results.sort(key=lambda o: (o.date, o.start_time, o.event_id or 0))
        return results

    # ── 作る ────────────────────────────────────────────────────────────

    def create_single_event(self, cmd: CreateSingleEventCommand) -> CalendarEvent:
        self._check_task(cmd.task_id, cmd.user_id)
        event = CalendarEvent.create_single(
            user_id=cmd.user_id,
            title=cmd.title,
            time_zone=TimeZoneId(cmd.time_zone),
            schedule=SingleEventSchedule(cmd.start_utc, cmd.duration_minutes),
            created_at=self._now(),
            location=cmd.location,
            description=cmd.description,
            color_key=cmd.color_key,
            task_id=cmd.task_id,
        )
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def create_recurring_event(self, cmd: CreateRecurringEventCommand) -> CalendarEvent:
        self._check_task(cmd.task_id, cmd.user_id)
        self._check_rule_calendar(cmd.recurrence_rule, cmd.user_id)
        event = CalendarEvent.create_recurring(
            user_id=cmd.user_id,
            title=cmd.title,
            time_zone=TimeZoneId(cmd.time_zone),
            schedule=RecurringEventSchedule(cmd.anchor_utc, cmd.duration_minutes, cmd.recurrence_rule),
            created_at=self._now(),
            location=cmd.location,
            description=cmd.description,
            color_key=cmd.color_key,
            task_id=cmd.task_id,
        )
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    # ── 直す ────────────────────────────────────────────────────────────

    def update_event(self, cmd: UpdateEventCommand) -> CalendarEvent:
        """詳細を置き換え、単発なら日時も移す（繰り返しの日時は ``update_recurring_series``）。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        self._check_task(cmd.task_id, cmd.user_id)
        now = self._now()
        event.change_details(
            title=cmd.title,
            location=cmd.location,
            description=cmd.description,
            task_id=cmd.task_id,
            updated_at=now,
        )
        if event.is_single() and cmd.start_utc is not None and cmd.duration_minutes is not None:
            event.reschedule_single(SingleEventSchedule(cmd.start_utc, cmd.duration_minutes), now)
        if cmd.color_key is not None:
            event.set_color(cmd.color_key, now)
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def reschedule_single_event(self, cmd: RescheduleSingleEventCommand) -> CalendarEvent:
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_single():
            raise ValidationError("reschedule is only valid for single events")
        event.reschedule_single(SingleEventSchedule(cmd.start_utc, cmd.duration_minutes), self._now())
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def update_recurring_series(self, cmd: UpdateRecurringSeriesCommand) -> CalendarEvent:
        """すべての回を直す。``anchor_utc`` を省くと先頭の回の瞬間は今のまま。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring() or event.recurring_schedule is None:
            raise ValidationError("update_recurring_series is only valid for recurring events")
        self._check_task(cmd.task_id, cmd.user_id)
        self._check_rule_calendar(cmd.recurrence_rule, cmd.user_id)
        now = self._now()
        event.change_details(
            title=cmd.title,
            location=cmd.location,
            description=cmd.description,
            task_id=cmd.task_id,
            updated_at=now,
        )
        anchor = cmd.anchor_utc if cmd.anchor_utc is not None else event.recurring_schedule.anchor_utc
        event.change_recurrence_schedule(
            RecurringEventSchedule(anchor, cmd.duration_minutes, cmd.recurrence_rule), now
        )
        event.set_color(cmd.color_key, now)
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def change_following_occurrences(self, cmd: ChangeFollowingOccurrencesCommand) -> CalendarEvent:
        """この回以降を新しい系列に分けて直す。新しい系列を返す。

        先頭の回から分けると元の系列に回が残らない（終了日が開始日より前になる）ので、
        そのときは元の系列を消し、新しい系列が全体を引き継ぐ。
        """
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring():
            raise ValidationError("change_following_occurrences is only valid for recurring events")
        task_id = event.task_id if cmd.task_id is UNSET else cmd.task_id
        self._check_task(task_id, cmd.user_id)
        self._check_rule_calendar(cmd.recurrence_rule, cmd.user_id)
        now = self._now()

        new_series = CalendarEvent.create_recurring(
            user_id=event.user_id,
            title=cmd.title,
            time_zone=event.time_zone,
            schedule=RecurringEventSchedule(cmd.anchor_utc, cmd.duration_minutes, cmd.recurrence_rule),
            created_at=now,
            location=cmd.location,
            description=cmd.description,
            color_key=cmd.color_key,
            task_id=task_id,
        )
        self._end_series_before(event, cmd.from_occurrence_key.date, now)
        saved = self._events.save(new_series)
        self._uow.commit()
        return saved

    def split_this_occurrence(self, cmd: SplitThisOccurrenceCommand) -> CalendarEvent:
        """この回だけを直す: 系列からその回を飛ばし、新しい単発を作って返す。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring():
            raise ValidationError("split_this_occurrence is only valid for recurring events")
        task_id = event.task_id if cmd.task_id is UNSET else cmd.task_id
        self._check_task(task_id, cmd.user_id)
        now = self._now()

        single = CalendarEvent.create_single(
            user_id=event.user_id,
            title=cmd.title,
            time_zone=event.time_zone,
            schedule=SingleEventSchedule(cmd.start_utc, cmd.duration_minutes),
            created_at=now,
            location=cmd.location,
            description=cmd.description,
            color_key=cmd.color_key,
            task_id=task_id,
        )
        event.skip_occurrence(cmd.occurrence_key, now)
        self._events.save(event)
        saved = self._events.save(single)
        self._uow.commit()
        return saved

    # ── 回の操作 ────────────────────────────────────────────────────────

    def skip_occurrence(self, cmd: OccurrenceCommand) -> CalendarEvent:
        """その回を飛ばす（「この回を削除」も同じ）。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        event.skip_occurrence(cmd.occurrence_key, self._now())
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    delete_occurrence = skip_occurrence

    def restore_occurrence(self, cmd: OccurrenceCommand) -> CalendarEvent:
        """飛ばした回を戻す。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        event.remove_occurrence_exception(cmd.occurrence_key, self._now())
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def move_occurrence(self, cmd: MoveOccurrenceCommand) -> CalendarEvent:
        """その回だけ別の日時へ移す。移した先は予定のタイムゾーンの壁時計で持つ。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring():
            raise ValidationError("move_occurrence is only valid for recurring events")
        zone = event.time_zone.zone
        event.move_occurrence(
            cmd.occurrence_key,
            new_date=local_date_of(cmd.start_utc, zone),
            new_start_time=local_time_of(cmd.start_utc, zone),
            duration_minutes=cmd.duration_minutes,
            title=cmd.title,
            location=cmd.location,
            updated_at=self._now(),
        )
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def cancel_move_occurrence(self, cmd: OccurrenceCommand) -> CalendarEvent:
        """移した回を系列どおりの位置へ戻す（元に戻す操作）。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring():
            raise ValidationError("cancel_move_occurrence is only valid for recurring events")
        event.remove_occurrence_move(cmd.occurrence_key, self._now())
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    # ── 消す ────────────────────────────────────────────────────────────

    def delete_event(self, event_id: int, user_id: int, expected_version: int | None = None) -> None:
        event = self._owned(event_id, user_id)
        event.ensure_version(expected_version)
        self._events.delete(event_id)
        self._uow.commit()

    def delete_following_occurrences(self, cmd: OccurrenceCommand) -> None:
        """この回以降を消す。先頭の回を指したら系列ごと消える。"""
        event = self._owned(cmd.event_id, cmd.user_id)
        event.ensure_version(cmd.expected_version)
        if not event.is_recurring():
            raise ValidationError("delete_following_occurrences is only valid for recurring events")
        self._end_series_before(event, cmd.occurrence_key.date, self._now())
        self._uow.commit()

    # ── 内側 ────────────────────────────────────────────────────────────

    def _end_series_before(self, event: CalendarEvent, from_date: date, now: datetime) -> None:
        """系列を ``from_date`` の前日で終える。先頭の回より前になるなら系列ごと消す。"""
        new_end = _shift_clamped(from_date, -1)
        if from_date <= event.series_start_date():
            assert event.id is not None
            self._events.delete(event.id)
            return
        event.change_recurrence_end_date(new_end, now)
        self._events.save(event)

    def _owned(self, event_id: int, user_id: int) -> CalendarEvent:
        return owned_by(
            self._events.find_by_id(event_id), user_id,
            resource="CalendarEvent", resource_id=event_id,
        )

    def _check_task(self, task_id: int | None, user_id: int) -> None:
        if task_id is None:
            return
        if self._tasks.find_by_id_for_user(task_id, user_id) is None:
            raise NotFoundError("Task", task_id)

    def _check_rule_calendar(self, rule: RecurrenceRule, user_id: int) -> None:
        calendar_id = rule.adjustment.calendar_id if rule.adjustment else None
        if calendar_id is None:
            return
        owned_by(
            self._calendars.find_by_id(calendar_id), user_id,
            resource="BusinessCalendar", resource_id=calendar_id,
        )

    def _calendar_for(
        self, event: CalendarEvent, cache: dict[int, BusinessCalendar | None]
    ) -> BusinessCalendar | None:
        """繰り返しの営業日シフトが参照するカレンダー（持ち主の違うものは使わない）。"""
        schedule = event.recurring_schedule
        if schedule is None or schedule.recurrence_rule.adjustment is None:
            return None
        calendar_id = schedule.recurrence_rule.adjustment.calendar_id
        if calendar_id is None:
            return None
        if calendar_id not in cache:
            found = self._calendars.find_by_id(calendar_id)
            cache[calendar_id] = found if found is not None and found.user_id == event.user_id else None
        return cache[calendar_id]


__all__ = ["CalendarEventUseCases"]
