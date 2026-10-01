"""予定（移植元 NolumiaScheduler の集約 ``CalendarEvent``、docs/time-model.md §10-1）。

単発（``SINGLE``）か繰り返し（``RECURRING``）のどちらか。繰り返しの個々の回への差分は
``exceptions``（飛ばす／内容の上書き）と ``moves``（別の日時へ移した回）で持つ。
回は ``OccurrenceKey``（予定のタイムゾーンでの候補日 ＋ 系列の開始時刻）で指す。

更新のたびに ``version`` が 1 つ進む（楽観ロック）。時刻は呼び出し側が渡す
（ドメインは時計を持たない）。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import (
    OccurrenceKey,
    RecurringEventSchedule,
    SingleEventSchedule,
)
from src.domain.value_objects.local_schedule_point import local_date_of, local_time_of
from src.domain.value_objects.time_zone import TimeZoneId

PERIOD_OVERLAP_MARGIN_DAYS = 31
"""期間で粗く絞るときに、有効な日付の範囲の両側へ足す日数。

営業日シフトで回が名目の範囲から数日はみ出しうるので、粗い絞り込みが本当にある回を
落とさないよう広めに取る（余分に拾っても、展開で正確に絞り直すので害は無い）。
"""


class EventKind(enum.StrEnum):
    SINGLE = "SINGLE"
    RECURRING = "RECURRING"


class ExceptionType(enum.StrEnum):
    SKIP = "SKIP"
    OVERRIDE = "OVERRIDE"
    """その回の内容の上書き。新しくは作らない（移植元の古いデータの読み込みのためだけに残す）。"""


@dataclass(frozen=True)
class ExceptionOverride:
    title: str | None = None
    location: str | None = None
    start_time: time | None = None
    duration_minutes: int | None = None

    def is_empty(self) -> bool:
        return (
            self.title is None and self.location is None
            and self.start_time is None and self.duration_minutes is None
        )


@dataclass(frozen=True)
class EventException:
    occurrence_key: OccurrenceKey
    type: ExceptionType
    override: ExceptionOverride | None = None

    @classmethod
    def skip(cls, key: OccurrenceKey) -> EventException:
        return cls(key, ExceptionType.SKIP)

    @classmethod
    def override_with(cls, key: OccurrenceKey, content: ExceptionOverride) -> EventException:
        return cls(key, ExceptionType.OVERRIDE, content)

    def rekeyed(self, key: OccurrenceKey) -> EventException:
        return EventException(key, self.type, self.override)


@dataclass(frozen=True)
class EventMove:
    """繰り返しの 1 回を別の日時へ移したもの。移した先は予定のタイムゾーンの壁時計で持つ。"""

    occurrence_key: OccurrenceKey
    new_date: date
    new_start_time: time | None = None
    new_duration_minutes: int | None = None
    title: str | None = None
    location: str | None = None

    def rekeyed(self, key: OccurrenceKey) -> EventMove:
        return EventMove(
            key, self.new_date, self.new_start_time, self.new_duration_minutes,
            self.title, self.location,
        )


def _check_title(title: str) -> None:
    if not title or not title.strip():
        raise ValidationError("title must not be empty")


@dataclass
class CalendarEvent:
    id: int | None
    user_id: int
    kind: EventKind
    title: str
    time_zone: TimeZoneId
    single_schedule: SingleEventSchedule | None = None
    recurring_schedule: RecurringEventSchedule | None = None
    location: str | None = None
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None
    """WBS のタスク（任意）。予定から作業の記録へつなぐため。"""
    exceptions: list[EventException] = field(default_factory=list)
    moves: list[EventMove] = field(default_factory=list)
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _check_title(self.title)
        if self.version < 1:
            raise ValidationError("version must be 1 or greater")
        if self.kind == EventKind.SINGLE:
            if self.single_schedule is None or self.recurring_schedule is not None:
                raise ValidationError("a single event needs exactly a single schedule")
        else:
            if self.recurring_schedule is None or self.single_schedule is not None:
                raise ValidationError("a recurring event needs exactly a recurring schedule")
            self._ensure_recurrence_starts_on_or_before_end(self.recurring_schedule)

    # ── 作る ────────────────────────────────────────────────────────────

    @classmethod
    def create_single(
        cls,
        *,
        user_id: int,
        title: str,
        time_zone: TimeZoneId,
        schedule: SingleEventSchedule,
        created_at: datetime,
        location: str | None = None,
        description: str | None = None,
        color_key: EventColorKey = EventColorKey.DEFAULT,
        task_id: int | None = None,
    ) -> CalendarEvent:
        return cls(
            id=None, user_id=user_id, kind=EventKind.SINGLE, title=title,
            time_zone=time_zone, single_schedule=schedule,
            location=location, description=description, color_key=color_key,
            task_id=task_id, created_at=created_at, updated_at=created_at,
        )

    @classmethod
    def create_recurring(
        cls,
        *,
        user_id: int,
        title: str,
        time_zone: TimeZoneId,
        schedule: RecurringEventSchedule,
        created_at: datetime,
        location: str | None = None,
        description: str | None = None,
        color_key: EventColorKey = EventColorKey.DEFAULT,
        task_id: int | None = None,
    ) -> CalendarEvent:
        return cls(
            id=None, user_id=user_id, kind=EventKind.RECURRING, title=title,
            time_zone=time_zone, recurring_schedule=schedule,
            location=location, description=description, color_key=color_key,
            task_id=task_id, created_at=created_at, updated_at=created_at,
        )

    # ── 問い合わせ ──────────────────────────────────────────────────────

    def is_single(self) -> bool:
        return self.kind == EventKind.SINGLE

    def is_recurring(self) -> bool:
        return self.kind == EventKind.RECURRING

    def has_exception_for(self, key: OccurrenceKey) -> bool:
        return any(e.occurrence_key == key for e in self.exceptions)

    def series_start_date(self) -> date:
        """繰り返しの先頭の回のローカル日（予定のタイムゾーン）。"""
        schedule = self._require_recurring()
        return local_date_of(schedule.anchor_utc, self.time_zone.zone)

    def ensure_version(self, expected_version: int | None) -> None:
        """楽観ロック。読んだときの版と違えば ``ConflictError``。``None`` は確かめない。"""
        if expected_version is not None and expected_version != self.version:
            raise ConflictError(
                f"calendar event {self.id} was changed (version {self.version}, expected {expected_version})"
            )

    def active_date_span(self) -> tuple[date, date]:
        """回が出うるローカル日の範囲（両端を含む）。粗い範囲であって、回の正確な集合ではない。

        単発は開始日〜終了日（終了がちょうど 0:00 なら前日まで）。繰り返しは先頭の回〜
        終了日で、移した回の行き先が外にあればそこまで広げる。
        """
        zone = self.time_zone.zone
        if self.is_single():
            single = self._require_single()
            start = local_date_of(single.start_utc, zone)
            end_local_date = local_date_of(single.end_utc, zone)
            end_at_midnight = local_time_of(single.end_utc, zone) == time(0, 0)
            end = (
                end_local_date - timedelta(days=1)
                if end_at_midnight and end_local_date > start
                else end_local_date
            )
            return (start, end) if start <= end else (end, start)

        schedule = self._require_recurring()
        span_start = local_date_of(schedule.anchor_utc, zone)
        span_end = schedule.recurrence_rule.end_date
        for move in self.moves:
            span_start = min(span_start, move.new_date)
            span_end = max(span_end, move.new_date)
        return span_start, span_end

    def indexed_day_span(self) -> tuple[int, int]:
        """``active_date_span`` を日の通し番号（``date.toordinal()``）にして余白を足したもの。

        表の索引付きの列（``span_start_day`` / ``span_end_day``）に入れ、回を展開せずに
        期間で粗く絞るために使う。
        """
        start, end = self.active_date_span()
        return (
            start.toordinal() - PERIOD_OVERLAP_MARGIN_DAYS,
            end.toordinal() + PERIOD_OVERLAP_MARGIN_DAYS,
        )

    def overlaps_period(self, from_date: date, to_date: date) -> bool:
        """余白込みの有効範囲が ``[from_date, to_date]`` と重なるか（粗い絞り込み）。"""
        start_day, end_day = self.indexed_day_span()
        return start_day <= to_date.toordinal() and end_day >= from_date.toordinal()

    # ── 直す ────────────────────────────────────────────────────────────

    def change_details(
        self,
        *,
        title: str,
        location: str | None,
        description: str | None,
        task_id: int | None,
        updated_at: datetime,
    ) -> None:
        _check_title(title)
        self.title = title
        self.location = location
        self.description = description
        self.task_id = task_id
        self._touch(updated_at)

    def set_color(self, color_key: EventColorKey, updated_at: datetime) -> None:
        if self.color_key == color_key:
            return
        self.color_key = color_key
        self._touch(updated_at)

    def reschedule_single(self, schedule: SingleEventSchedule, updated_at: datetime) -> None:
        self._require_single()
        self.single_schedule = schedule
        self._touch(updated_at)

    def change_recurrence_end_date(self, end_date: date, updated_at: datetime) -> None:
        schedule = self._require_recurring()
        new_schedule = schedule.with_recurrence_rule(schedule.recurrence_rule.with_end_date(end_date))
        self._ensure_recurrence_starts_on_or_before_end(new_schedule)
        self.recurring_schedule = new_schedule
        self._touch(updated_at)

    def change_recurrence_schedule(
        self, schedule: RecurringEventSchedule, updated_at: datetime
    ) -> None:
        """系列の時刻・規則を差し替える。

        回の鍵は（候補日, 系列の開始時刻）なので、開始時刻が変わると既存の飛ばす・上書き・
        移動がどの回も指さなくなる。開始時刻が変わったら鍵を付け替える。
        """
        old = self._require_recurring()
        self._ensure_recurrence_starts_on_or_before_end(schedule)
        zone = self.time_zone.zone
        old_start_time = local_time_of(old.anchor_utc, zone)
        new_start_time = local_time_of(schedule.anchor_utc, zone)
        if old_start_time != new_start_time:
            self._rekey_occurrence_customizations(old_start_time, new_start_time)
        self.recurring_schedule = schedule
        self._touch(updated_at)

    def skip_occurrence(self, key: OccurrenceKey, updated_at: datetime) -> None:
        """その回を飛ばす。同じ回の上書きがあれば飛ばすで置き換える（2 度目も飛ばすのまま）。"""
        self._require_recurring()
        self._remove_exception(key)
        self.exceptions.append(EventException.skip(key))
        self._touch(updated_at)

    def remove_occurrence_exception(self, key: OccurrenceKey, updated_at: datetime) -> None:
        """飛ばす（または上書き）を取り消して、その回を系列どおりに戻す。"""
        self._require_recurring()
        if not self._remove_exception(key):
            raise NotFoundError("OccurrenceException", _key_label(key))
        self._touch(updated_at)

    def move_occurrence(
        self,
        key: OccurrenceKey,
        *,
        new_date: date,
        new_start_time: time,
        duration_minutes: int,
        title: str | None,
        location: str | None,
        updated_at: datetime,
    ) -> None:
        """その回だけ別の日時へ移す。同じ回をもう一度移したら、前の移動を置き換える。"""
        self._require_recurring()
        if duration_minutes <= 0:
            raise ValidationError("duration_minutes must be greater than zero")
        self.moves = [m for m in self.moves if m.occurrence_key != key]
        self.moves.append(
            EventMove(key, new_date, new_start_time, duration_minutes, title, location)
        )
        self._touch(updated_at)

    def remove_occurrence_move(self, key: OccurrenceKey, updated_at: datetime) -> None:
        """移した回を系列どおりの位置へ戻す。"""
        self._require_recurring()
        remaining = [m for m in self.moves if m.occurrence_key != key]
        if len(remaining) == len(self.moves):
            raise NotFoundError("OccurrenceMove", _key_label(key))
        self.moves = remaining
        self._touch(updated_at)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _require_single(self) -> SingleEventSchedule:
        if self.kind != EventKind.SINGLE or self.single_schedule is None:
            raise ValidationError("this operation is only allowed for single events")
        return self.single_schedule

    def _require_recurring(self) -> RecurringEventSchedule:
        if self.kind != EventKind.RECURRING or self.recurring_schedule is None:
            raise ValidationError("this operation is only allowed for recurring events")
        return self.recurring_schedule

    def _ensure_recurrence_starts_on_or_before_end(self, schedule: RecurringEventSchedule) -> None:
        # 不変条件: アンカーのローカル日（予定のタイムゾーンで解く）は終了日以前。
        # 規則とタイムゾーンの両方にまたがるので、値オブジェクトではなく集約で見る。
        anchor_local_date = local_date_of(schedule.anchor_utc, self.time_zone.zone)
        if anchor_local_date > schedule.recurrence_rule.end_date:
            raise ValidationError("start date must be on or before the recurrence end date")

    def _rekey_occurrence_customizations(self, old_time: time, new_time: time) -> None:
        self.exceptions = [
            e.rekeyed(OccurrenceKey(e.occurrence_key.date, new_time))
            if e.occurrence_key.time == old_time else e
            for e in self.exceptions
        ]
        self.moves = [
            m.rekeyed(OccurrenceKey(m.occurrence_key.date, new_time))
            if m.occurrence_key.time == old_time else m
            for m in self.moves
        ]

    def _remove_exception(self, key: OccurrenceKey) -> bool:
        for index, existing in enumerate(self.exceptions):
            if existing.occurrence_key == key:
                del self.exceptions[index]
                return True
        return False

    def _touch(self, updated_at: datetime) -> None:
        self.updated_at = updated_at
        self.version += 1


def _key_label(key: OccurrenceKey) -> str:
    return f"{key.date.isoformat()}T{key.time.isoformat() if key.time else ''}"


__all__ = [
    "PERIOD_OVERLAP_MARGIN_DAYS",
    "CalendarEvent",
    "EventException",
    "EventKind",
    "EventMove",
    "ExceptionOverride",
    "ExceptionType",
]
