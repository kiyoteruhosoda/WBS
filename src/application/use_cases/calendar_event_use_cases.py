"""予定のユースケース（移植元 ``CalendarEventApplicationService``）。

- 期間で引く: ``find_by_period``（予定）・``list_occurrences``（展開した回）
- 作る・直す: 単発／繰り返し、すべて・この回以降・この回だけ
- 回の操作: 飛ばす・飛ばすの取り消し・移動・移動の取り消し
- 消す: 予定ごと・この回以降
- 済み: 分類がタスクの予定の回に済みを付ける・外す（ADR-0025）

どの操作も ``user_id`` で持ち主を確かめる（他人の予定は「無い」として扱う）。
時刻は UTC の瞬間 ＋ 長さ（分）で受け取り、作成・更新の時刻は ``now``
（既定は ``src.shared.clock.utcnow``）で付ける。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta

from src.application.dto.calendar_event_dto import (
    ChangeFollowingOccurrencesCommand,
    CreateRecurringEventCommand,
    CreateSingleEventCommand,
    MoveOccurrenceCommand,
    OccurrenceCommand,
    OccurrenceDoneCommand,
    OccurrenceView,
    PlannedAlarm,
    RescheduleSingleEventCommand,
    SplitThisOccurrenceCommand,
    UpdateEventCommand,
    UpdateRecurringSeriesCommand,
)
from src.application.dto.unset import UNSET, UnsetType
from src.application.ports.day_off_layers_source import DayOffLayersSource
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.calendar import Calendar
from src.domain.entities.calendar_event import (
    PERIOD_OVERLAP_MARGIN_DAYS,
    CalendarEvent,
    ExceptionType,
)
from src.domain.entities.occurrence_completion import OccurrenceCompletion
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.repositories.calendar_repository import CalendarRepository
from src.domain.repositories.occurrence_completion_repository import (
    OccurrenceCompletionRepository,
)
from src.domain.services.day_off_layers import DayOffLayers
from src.domain.services.default_calendar import ensure_default_calendar
from src.domain.services.occurrence_display_projection import to_display_time_zone
from src.domain.services.occurrence_expander import OccurrenceExpander
from src.domain.value_objects.event_alarm import ALARM_OFFSETS_MINUTES, EventAlarm
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import (
    EventOccurrence,
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.local_schedule_point import (
    local_date_of,
    local_time_of,
    start_instant,
    to_naive_utc,
)
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow

SCHEDULED_TASK_LOOKBACK_DAYS = 7
"""打刻の既定のタスクを探すとき、何日前に始まった回まで見るか（それより長い予定は見ない）。"""

MAX_ALARM_WINDOW = timedelta(days=7)
"""この先の通知を一度に引ける期間の上限（ADR-0021）。"""

_ALARM_EXPANSION_PAD_DAYS = 2
"""通知の期間（UTC の瞬間）を予定のタイムゾーンのローカル日へ直すときの余白。UTC からのずれは
最大でも ±14 時間なので、前後 1 日で足りるが、日付の境目の丸めも含めて 2 日取る。"""


def _alarm_or_default(alarm: EventAlarm | None | UnsetType) -> EventAlarm | None:
    """作るときの通知。省かれたら既定（移植元 ``EventAlarm.Default``: 4 つとも入り）。"""
    return EventAlarm.default() if isinstance(alarm, UnsetType) else alarm


def _alarm_or(alarm: EventAlarm | None | UnsetType, current: EventAlarm | None) -> EventAlarm | None:
    """直すときの通知。省かれたら ``current``（今のもの・元の系列のもの）。"""
    return current if isinstance(alarm, UnsetType) else alarm


def _shift_clamped(day: date, days: int) -> date:
    try:
        return day + timedelta(days=days)
    except OverflowError:
        return date.max if days > 0 else date.min


class CalendarEventUseCases:
    def __init__(
        self,
        events: CalendarEventRepository,
        tasks: OwnedTaskLookup,
        unit_of_work: UnitOfWork,
        *,
        expander: OccurrenceExpander | None = None,
        now: Callable[[], datetime] = utcnow,
        completions: OccurrenceCompletionRepository | None = None,
        event_calendars: CalendarRepository | None = None,
        day_off_layers: DayOffLayersSource | None = None,
    ) -> None:
        self._events = events
        # 休みの層（ADR-0029）。営業日シフトはこの判定だけを使う（無ければ月〜金・休みの日なし）。
        self._day_off_layers = day_off_layers
        # 予定のカレンダー（ADR-0027）。無ければカレンダーを決めずに保存する（保存先が既定へ入れる）。
        self._event_calendars = event_calendars
        # 回の済み（ADR-0025）。無ければ済みは出さない（どの回も済みでない）。
        self._completions = completions
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
        pairs = self._expand(user_id, from_date, to_date, viewer_time_zone)
        return [occurrence for _, occurrence in pairs]

    def list_occurrence_views(
        self, user_id: int, from_date: date, to_date: date, viewer_time_zone: str
    ) -> list[OccurrenceView]:
        """``list_occurrences`` を閲覧者のゾーンで行い、画面へ渡す形（``OccurrenceView``）にする。

        開始の UTC 瞬間は、投影した壁時計を閲覧者のゾーンで瞬間へ戻して出す（終日の回は
        ずらさないので、閲覧者のその日の 0:00 になる）。
        """
        viewer = TimeZoneId(viewer_time_zone)
        pairs = self._expand(user_id, from_date, to_date, viewer_time_zone)
        done = self._done_keys(event for event, _ in pairs if event.is_task())
        calendars = self._calendars_by_id(user_id)
        return [
            OccurrenceView(
                event_id=event.id,
                event_version=event.version,
                is_recurring=event.is_recurring(),
                title=occurrence.title,
                start_utc=start_instant(occurrence.date, occurrence.start_time, viewer.zone),
                duration_minutes=occurrence.duration_minutes,
                date=occurrence.date,
                start_time=occurrence.start_time,
                is_all_day=occurrence.is_all_day,
                color_key=occurrence.color_key,
                location=occurrence.location,
                task_id=occurrence.task_id,
                is_moved=occurrence.is_moved,
                is_overridden=occurrence.is_overridden,
                series_key=occurrence.series_key if event.is_recurring() else None,
                alarm=event.alarm,
                event_type=event.event_type,
                is_done=event.is_task()
                and (event.id, _completion_key_of(event, occurrence)) in done,
                calendar_id=event.calendar_id,
                calendar_color_key=calendars[event.calendar_id].color_key
                if event.calendar_id in calendars
                else EventColorKey.DEFAULT,
                is_private=event.calendar_id in calendars and calendars[event.calendar_id].is_private,
            )
            for event, occurrence in pairs
            if event.id is not None
        ]

    def list_planned_alarms(
        self, user_id: int, from_utc: datetime, to_utc: datetime
    ) -> list[PlannedAlarm]:
        """``[from_utc, to_utc)`` に知らせる時刻が来る通知を、知らせる時刻の順に返す（ADR-0021）。

        回の展開は ``/calendar/occurrences`` と同じ（繰り返し・営業日シフト・祝日・移した回。
        飛ばした回は出ない）。知らせるのは通知を持ち、止めていない予定の、終日でない回だけ
        （終日の回には意味のある開始時刻が無い。移植元と同じ）。基準は回の開始時刻で、長さは
        見ない。期間は ``MAX_ALARM_WINDOW`` まで。超えたら・逆なら ``ValidationError``。
        「遅れても 1 分以内なら鳴らす」は端末の仕事（ここは予定を返すだけ）。
        """
        start = to_naive_utc(from_utc)
        end = to_naive_utc(to_utc)
        if start >= end:
            raise ValidationError("from must be before to")
        if end - start > MAX_ALARM_WINDOW:
            raise ValidationError(
                f"the window must be {MAX_ALARM_WINDOW.days} days or shorter"
            )
        # 知らせる時刻は開始より前（最大 15 分）なので、開始は [start, end + 15 分) にある。
        latest_start = end + timedelta(minutes=max(ALARM_OFFSETS_MINUTES))
        pairs = self._expand(
            user_id,
            _shift_clamped(start.date(), -_ALARM_EXPANSION_PAD_DAYS),
            _shift_clamped(latest_start.date(), _ALARM_EXPANSION_PAD_DAYS),
            None,
            with_alarm_only=True,
        )
        task_titles: dict[int, str | None] = {}
        planned: list[PlannedAlarm] = []
        for event, occurrence in pairs:
            if event.id is None or event.alarm is None or occurrence.is_all_day:
                continue
            occurrence_start = start_instant(
                occurrence.date, occurrence.start_time, event.time_zone.zone
            )
            for minutes_before in event.alarm.minutes_before():
                notify_at = occurrence_start - timedelta(minutes=minutes_before)
                if not start <= notify_at < end:
                    continue
                task_id = occurrence.task_id
                task_title = self._task_title(task_id, user_id, task_titles)
                planned.append(
                    PlannedAlarm(
                        event_id=event.id,
                        occurrence_start_utc=occurrence_start,
                        minutes_before=minutes_before,
                        notify_at_utc=notify_at,
                        title=occurrence.title,
                        duration_minutes=occurrence.duration_minutes,
                        location=occurrence.location,
                        task_id=task_id if task_title is not None else None,
                        task_title=task_title,
                        is_recurring=event.is_recurring(),
                    )
                )
        planned.sort(
            key=lambda p: (p.notify_at_utc, p.occurrence_start_utc, p.event_id, -p.minutes_before)
        )
        return planned

    def task_scheduled_at(self, user_id: int, at: datetime) -> int | None:
        """``at``（naive な UTC）に掛かっている回に結ばれた、その利用者のタスク（打刻の既定、ADR-0008）。

        ``ScheduledTaskLookup`` の実装。回が重なっていたら、いちばん後に始まった回を選ぶ
        （同時なら短い方、さらに同じなら予定の id の小さい方）。始まりが 1 週間より前の
        回（長い予定）は見ない。結んだタスクが消えている・他人のものなら飛ばす。
        """
        instant = to_naive_utc(at)
        day = instant.date()
        candidates: list[tuple[datetime, int, int, int]] = []
        private = self._private_calendar_ids(user_id)
        for event, occurrence in self._expand(
            user_id,
            _shift_clamped(day, -SCHEDULED_TASK_LOOKBACK_DAYS),
            _shift_clamped(day, 1),
            None,
        ):
            if occurrence.task_id is None or event.id is None or event.calendar_id in private:
                continue
            start = start_instant(occurrence.date, occurrence.start_time, event.time_zone.zone)
            if not start <= instant < start + timedelta(minutes=occurrence.duration_minutes):
                continue
            candidates.append((start, occurrence.duration_minutes, event.id, occurrence.task_id))
        candidates.sort(key=lambda c: (c[1], c[2]))  # 短い方・id の小さい方
        candidates.sort(key=lambda c: c[0], reverse=True)  # 後に始まった方（安定ソート）
        for _, _, _, task_id in candidates:
            if self._tasks.find_by_id_for_user(task_id, user_id) is not None:
                return task_id
        return None

    def scheduled_minutes_by_task(
        self, user_id: int, from_date: date, to_date: date, time_zone: str
    ) -> dict[int, int]:
        """``[from_date, to_date]``（``time_zone`` のローカル日）の回の長さを、結ばれたタスクごとに足す。

        ``ScheduledTimeLookup`` の実装（タスクの「予定済みの時間」、ADR-0014）。数えるのは
        その利用者の予定だけ（引く段で ``user_id`` で絞る）。終日の回は「その日に充てる」印で
        作業の時間ではないので数えない。回の日付は ``time_zone`` へ投影したもので見る。
        """
        totals: dict[int, int] = {}
        private = self._private_calendar_ids(user_id)
        for event, occurrence in self._expand(
            user_id, from_date, to_date, time_zone, linked_to_tasks_only=True
        ):
            if occurrence.task_id is None or occurrence.is_all_day or event.calendar_id in private:
                continue
            totals[occurrence.task_id] = (
                totals.get(occurrence.task_id, 0) + occurrence.duration_minutes
            )
        return totals

    def _expand(
        self,
        user_id: int,
        from_date: date,
        to_date: date,
        viewer_time_zone: str | None,
        *,
        linked_to_tasks_only: bool = False,
        with_alarm_only: bool = False,
    ) -> list[tuple[CalendarEvent, EventOccurrence]]:
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        viewer = TimeZoneId(viewer_time_zone) if viewer_time_zone else None
        pad = 1 if viewer else 0
        expand_from = _shift_clamped(from_date, -pad)
        expand_to = _shift_clamped(to_date, pad)

        calendars = _ShiftCalendars(self, user_id)
        results: list[tuple[CalendarEvent, EventOccurrence]] = []
        for event in self._events.find_by_period(user_id, expand_from, expand_to):
            if linked_to_tasks_only and event.task_id is None:
                continue
            if with_alarm_only and (event.alarm is None or not event.alarm.minutes_before()):
                continue
            calendar = calendars.for_event(event)
            for occurrence in self._expander.expand(event, expand_from, expand_to, calendar):
                if viewer is not None:
                    occurrence = to_display_time_zone(occurrence, event.time_zone, viewer)
                    if not from_date <= occurrence.date <= to_date:
                        continue
                results.append((event, occurrence))
        results.sort(key=lambda pair: (pair[1].date, pair[1].start_time, pair[1].event_id or 0))
        return results

    # ── 作る ────────────────────────────────────────────────────────────

    def create_single_event(self, cmd: CreateSingleEventCommand) -> CalendarEvent:
        self._check_task(cmd.task_id, cmd.user_id)
        calendar_id = self._calendar_for_new_event(cmd.calendar_id, cmd.user_id)
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
            alarm=_alarm_or_default(cmd.alarm),
            event_type=cmd.event_type,
            calendar_id=calendar_id,
        )
        self._ensure_fits_calendar(event)
        saved = self._events.save(event)
        self._uow.commit()
        return saved

    def create_recurring_event(self, cmd: CreateRecurringEventCommand) -> CalendarEvent:
        self._check_task(cmd.task_id, cmd.user_id)
        calendar_id = self._calendar_for_new_event(cmd.calendar_id, cmd.user_id)
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
            alarm=_alarm_or_default(cmd.alarm),
            event_type=cmd.event_type,
            calendar_id=calendar_id,
        )
        self._ensure_fits_calendar(event)
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
            event_type=cmd.event_type,
        )
        if event.is_single() and cmd.start_utc is not None and cmd.duration_minutes is not None:
            event.reschedule_single(SingleEventSchedule(cmd.start_utc, cmd.duration_minutes), now)
        if cmd.color_key is not None:
            event.set_color(cmd.color_key, now)
        self._move_to_calendar(event, cmd.calendar_id, now)
        event.set_alarm(_alarm_or(cmd.alarm, event.alarm), now)
        self._ensure_fits_calendar(event)
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
        now = self._now()
        event.change_details(
            title=cmd.title,
            location=cmd.location,
            description=cmd.description,
            task_id=cmd.task_id,
            updated_at=now,
            event_type=cmd.event_type,
        )
        anchor = cmd.anchor_utc if cmd.anchor_utc is not None else event.recurring_schedule.anchor_utc
        old_start_time = event.series_start_time()
        event.change_recurrence_schedule(
            RecurringEventSchedule(anchor, cmd.duration_minutes, cmd.recurrence_rule), now
        )
        # 系列の開始時刻が変わったら、例外・移動と同じく済みの鍵も付け替える。
        self._rekey_completions(event, old_start_time, event.series_start_time())
        event.set_color(cmd.color_key, now)
        self._move_to_calendar(event, cmd.calendar_id, now)
        event.set_alarm(_alarm_or(cmd.alarm, event.alarm), now)
        self._ensure_fits_calendar(event)
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
        calendar_id = self._calendar_or_current(cmd.calendar_id, event)
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
            alarm=_alarm_or(cmd.alarm, event.alarm),
            event_type=cmd.event_type or event.event_type,
            calendar_id=calendar_id,
        )
        self._ensure_fits_calendar(new_series)
        # この回以降の済みは新しい系列へ移す（鍵の時刻は新しい系列の開始時刻）。
        carried = [
            c for c in self._completions_of(event)
            if c.occurrence_key is not None and c.occurrence_key.date >= cmd.from_occurrence_key.date
        ]
        self._end_series_before(event, cmd.from_occurrence_key.date, now)
        saved = self._events.save(new_series)
        if carried and saved.is_task():
            assert saved.id is not None and self._completions is not None
            new_time = saved.series_start_time()
            self._completions.replace_for_event(
                saved.id,
                [
                    c.rekeyed(OccurrenceKey(c.occurrence_key.date, new_time), saved.id)
                    for c in carried
                    if c.occurrence_key is not None
                ],
            )
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
        calendar_id = self._calendar_or_current(cmd.calendar_id, event)
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
            alarm=_alarm_or(cmd.alarm, event.alarm),
            event_type=cmd.event_type or event.event_type,
            calendar_id=calendar_id,
        )
        self._ensure_fits_calendar(single)
        event.skip_occurrence(cmd.occurrence_key, now)
        self._events.save(event)
        saved = self._events.save(single)
        # 切り出した回に済みが付いていたら、新しい単発へ移す（飛ばした回には残さない）。
        completions = self._completions_of(event)
        moved = [c for c in completions if c.occurrence_key == cmd.occurrence_key]
        if moved:
            assert event.id is not None and saved.id is not None and self._completions is not None
            self._completions.replace_for_event(
                event.id, [c for c in completions if c.occurrence_key != cmd.occurrence_key]
            )
            if saved.is_task():
                self._completions.replace_for_event(saved.id, [moved[0].rekeyed(None, saved.id)])
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

    # ── 済み（ADR-0025）────────────────────────────────────────────────

    def set_occurrence_done(self, cmd: OccurrenceDoneCommand) -> bool:
        """タスクの分類の予定の回に済みを付ける（``done``）・外す。済みかどうかを返す。

        予定の版は進めない（済みは予定の中身ではない）。付けるのも外すのも、もうそうなって
        いればそのまま（何度送っても同じ）。

        - 予定の分類が「予定」なら ``ValidationError``
        - 単発は鍵なし（``occurrence_key`` が ``None``）、繰り返しは鍵が要る
        - 繰り返しの鍵は、その系列に本当にある回（飛ばした回は無い。移した回は元の鍵で指す）
        """
        if self._completions is None:
            raise ValidationError("occurrence completions are not available")
        event = self._owned(cmd.event_id, cmd.user_id)
        assert event.id is not None
        if not event.is_task():
            raise ValidationError("only task-type events can be marked as done")
        key = cmd.occurrence_key
        if event.is_single():
            if key is not None:
                raise ValidationError("a single event has no occurrence key")
        else:
            if key is None:
                raise ValidationError("a recurring event needs the occurrence key")
            if not self._has_occurrence(event, key):
                raise NotFoundError("Occurrence", f"{event.id}:{key.date.isoformat()}")

        completions = self._completions_of(event)
        others = [c for c in completions if c.occurrence_key != key]
        already = len(others) != len(completions)
        if cmd.done and not already:
            self._completions.replace_for_event(
                event.id, [*completions, OccurrenceCompletion(event.id, key, self._now())]
            )
        elif not cmd.done and already:
            self._completions.replace_for_event(event.id, others)
        self._uow.commit()
        return cmd.done

    # ── 消す ────────────────────────────────────────────────────────────

    def delete_event(self, event_id: int, user_id: int, expected_version: int | None = None) -> None:
        event = self._owned(event_id, user_id)
        event.ensure_version(expected_version)
        self._forget_completions(event_id)
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
        assert event.id is not None
        if from_date <= event.series_start_date():
            self._forget_completions(event.id)
            self._events.delete(event.id)
            return
        event.change_recurrence_end_date(new_end, now)
        self._events.save(event)
        # 終えた後ろの回の済みは消す（もう出ない回）。
        completions = self._completions_of(event)
        kept = [
            c for c in completions
            if c.occurrence_key is None or c.occurrence_key.date < from_date
        ]
        if len(kept) != len(completions):
            assert self._completions is not None
            self._completions.replace_for_event(event.id, kept)

    def _completions_of(self, event: CalendarEvent) -> list[OccurrenceCompletion]:
        if self._completions is None or event.id is None:
            return []
        return self._completions.find_by_events([event.id])

    def _forget_completions(self, event_id: int) -> None:
        # ⚠ SQLite は外部キーの ON DELETE CASCADE を効かせていないので、予定より先に消す。
        if self._completions is not None:
            self._completions.replace_for_event(event_id, [])

    def _done_keys(
        self, events: Iterable[CalendarEvent]
    ) -> set[tuple[int, OccurrenceKey | None]]:
        if self._completions is None:
            return set()
        ids = {e.id for e in events if e.id is not None}
        return {(c.event_id, c.occurrence_key) for c in self._completions.find_by_events(ids)}

    def _rekey_completions(self, event: CalendarEvent, old_time: time, new_time: time) -> None:
        if old_time == new_time or self._completions is None or event.id is None:
            return
        completions = self._completions.find_by_events([event.id])
        if not any(c.occurrence_key is not None and c.occurrence_key.time == old_time for c in completions):
            return
        self._completions.replace_for_event(
            event.id,
            [
                c.rekeyed(OccurrenceKey(c.occurrence_key.date, new_time))
                if c.occurrence_key is not None and c.occurrence_key.time == old_time
                else c
                for c in completions
            ],
        )

    def _has_occurrence(self, event: CalendarEvent, key: OccurrenceKey) -> bool:
        """``key`` が系列に今ある回か（飛ばした回・候補でない日は無い）。"""
        if any(m.occurrence_key == key for m in event.moves) and not any(
            e.occurrence_key == key and e.type == ExceptionType.SKIP for e in event.exceptions
        ):
            return True
        # 営業日シフトで回は候補日から動きうるので、候補日の前後を広めに展開して鍵で探す。
        calendar = _ShiftCalendars(self, event.user_id).for_event(event)
        found = self._expander.expand(
            event,
            _shift_clamped(key.date, -PERIOD_OVERLAP_MARGIN_DAYS),
            _shift_clamped(key.date, PERIOD_OVERLAP_MARGIN_DAYS),
            calendar,
        )
        return any(o.series_key == key for o in found)

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

    def _layers_for(self, user_id: int) -> DayOffLayers:
        return self._day_off_layers.layers_for(user_id) if self._day_off_layers else DayOffLayers()

    def _task_title(
        self, task_id: int | None, user_id: int, cache: dict[int, str | None]
    ) -> str | None:
        """結んだタスクの題名（消えた・他人のものなら ``None``）。"""
        if task_id is None:
            return None
        if task_id not in cache:
            task = self._tasks.find_by_id_for_user(task_id, user_id)
            cache[task_id] = task.title if task is not None else None
        return cache[task_id]

    # ── カレンダー（ADR-0027）────────────────────────────────────────────

    def _owned_calendar_id(self, calendar_id: int, user_id: int) -> int:
        """自分のカレンダーか確かめる（他人・無いものは 404）。"""
        if self._event_calendars is None:
            raise NotFoundError("Calendar", calendar_id)
        calendar = owned_by(
            self._event_calendars.find_by_id(calendar_id), user_id,
            resource="Calendar", resource_id=calendar_id,
        )
        if not calendar.holds_events:
            # 休みの層（ADR-0029）には予定を入れない。
            raise ValidationError("events can only be put into an events calendar")
        return calendar_id

    def _calendar_for_new_event(self, calendar_id: int | None, user_id: int) -> int | None:
        """作る予定のカレンダー。省けば既定のカレンダー。"""
        if calendar_id is not None:
            return self._owned_calendar_id(calendar_id, user_id)
        if self._event_calendars is None:
            return None
        return ensure_default_calendar(self._event_calendars, user_id, self._now()).id

    def _calendar_or_current(self, calendar_id: int | None, event: CalendarEvent) -> int | None:
        """切り出す・分ける予定のカレンダー。省けば元の系列のもの。"""
        if calendar_id is not None:
            return self._owned_calendar_id(calendar_id, event.user_id)
        return event.calendar_id

    def _move_to_calendar(self, event: CalendarEvent, calendar_id: int | None, now: datetime) -> None:
        if calendar_id is None:
            return
        event.move_to_calendar(self._owned_calendar_id(calendar_id, event.user_id), now)

    def _calendars_by_id(self, user_id: int) -> dict[int, Calendar]:
        if self._event_calendars is None:
            return {}
        return {c.id: c for c in self._event_calendars.find_all(user_id) if c.id is not None}

    def _private_calendar_ids(self, user_id: int) -> set[int]:
        """プライベートのカレンダー（ADR-0033。計画・打刻の既定のタスクに数えない）。"""
        return {cid for cid, c in self._calendars_by_id(user_id).items() if c.is_private}

    def _ensure_fits_calendar(self, event: CalendarEvent) -> None:
        """プライベートのカレンダーにタスクを結んだ予定は入れない（ADR-0033）。"""
        if event.calendar_id is None or self._event_calendars is None:
            return
        if event.task_id is None and not event.is_task():
            return
        calendar = self._event_calendars.find_by_id(event.calendar_id)
        if calendar is not None and calendar.is_private:
            raise ValidationError("a private calendar cannot hold events linked to tasks")


class _ShiftCalendars:
    """展開 1 回ぶんの、営業日シフトに渡す休みの層（利用者の層は 1 回だけ引く）。

    繰り返しの規則は営業日シフトを持つものだけが層を使う。層は表示の選択に関係なく
    「休みとして数える」で決まる（ADR-0029。古い営業日カレンダーの名指しは ADR-0032 で畳んだ）。
    """

    def __init__(self, owner: CalendarEventUseCases, user_id: int) -> None:
        self._owner = owner
        self._user_id = user_id
        self._layers: DayOffLayers | None = None

    def for_event(self, event: CalendarEvent) -> DayOffLayers | None:
        schedule = event.recurring_schedule
        if schedule is None or schedule.recurrence_rule.adjustment is None:
            return None
        if self._layers is None:
            self._layers = self._owner._layers_for(self._user_id)
        return self._layers


def _completion_key_of(event: CalendarEvent, occurrence: EventOccurrence) -> OccurrenceKey | None:
    """済みを引く鍵。単発は ``None``（投影で ``series_key`` が埋まっていても使わない）。"""
    return occurrence.series_key if event.is_recurring() else None


__all__ = ["CalendarEventUseCases"]
