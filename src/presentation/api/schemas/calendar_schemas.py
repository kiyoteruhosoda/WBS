"""予定・営業日カレンダーの API スキーマ（task #156、ADR-0009）。

時刻の入力は **UTC の瞬間（``Z`` 付き ISO 8601。オフセット付きも可）＋ 長さ（分）**。オフセットの
無い値は UTC とみなす。分の単位まで（秒・小数秒は 422）。繰り返しの回は ``occurrence``
（予定のタイムゾーンでの候補日 ``date`` ＋ 系列の開始時刻 ``start_time``）で指す。回の一覧の
``series_key`` をそのまま返せばよい。``expected_version`` は楽観ロックで、読んだときの版と
違えば 409。
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from src.application.dto.calendar_event_dto import OccurrenceView
from src.application.recurrence_rule_mapping import (
    recurrence_rule_from_mapping,
    recurrence_rule_to_mapping,
)
from src.domain.entities.business_calendar import BusinessCalendar, Holiday
from src.domain.entities.calendar_event import CalendarEvent
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.recurrence import (
    AdjustmentAction,
    AdjustmentCondition,
    AdjustmentShiftUnit,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
)
from src.presentation.api.schemas.types import UtcDatetime

TITLE_MAX = 500
MAX_DURATION_MINUTES = 366 * 24 * 60


def _minute_precision(value: dt.datetime) -> dt.datetime:
    if value.second or value.microsecond:
        raise ValueError("must be a whole minute (no seconds)")
    return value


MinuteInstant = Annotated[dt.datetime, AfterValidator(_minute_precision)]
"""入力の瞬間。分の単位まで（回の鍵が壁時計の時刻なので、秒を持たせない）。"""


def format_wall_time(value: dt.time) -> str:
    """``HH:MM``（秒があるときだけ ``HH:MM:SS``）。"""
    return value.strftime("%H:%M:%S" if value.second else "%H:%M")


# ── 繰り返しの規則 ──────────────────────────────────────────────────────────


class WeeklyRuleSchema(BaseModel):
    weekdays: list[Weekday] = Field(min_length=1)


class MonthlyRuleSchema(BaseModel):
    """``DAY_OF_MONTH``（``day``）・``NTH_WEEKDAY``（``week_index`` 1〜5 / -1=最終・``weekday``）・``LAST_DAY``。"""

    kind: Literal["DAY_OF_MONTH", "NTH_WEEKDAY", "LAST_DAY"]
    day: int | None = None
    week_index: int | None = None
    weekday: Weekday | None = None


class YearlyRuleSchema(BaseModel):
    """``DAY_OF_MONTH``（``month``・``day``）・``NTH_WEEKDAY``（``month``・``week_index``・``weekday``）。"""

    kind: Literal["DAY_OF_MONTH", "NTH_WEEKDAY"]
    month: int
    day: int | None = None
    week_index: int | None = None
    weekday: Weekday | None = None


class AdjustmentRuleSchema(BaseModel):
    """営業日シフト。``shift_amount`` が負なら前倒し。``calendar_id`` は自分の営業日カレンダー。"""

    condition: AdjustmentCondition
    shift_unit: AdjustmentShiftUnit
    shift_amount: int
    calendar_id: int | None = None
    action: AdjustmentAction = AdjustmentAction.SHIFT


class RecurrenceRuleSchema(BaseModel):
    """繰り返しの規則。``type`` に応じて ``weekly`` / ``monthly`` / ``yearly`` のどれか 1 つを持つ。"""

    type: RecurrenceType
    interval: int = Field(default=1, ge=1)
    end_date: dt.date | None = Field(default=None, description="null は終了日なし")
    weekly: WeeklyRuleSchema | None = None
    monthly: MonthlyRuleSchema | None = None
    yearly: YearlyRuleSchema | None = None
    adjustment: AdjustmentRuleSchema | None = None

    def to_rule(self) -> RecurrenceRule:
        return recurrence_rule_from_mapping(self.model_dump(mode="json"))

    @classmethod
    def from_rule(cls, rule: RecurrenceRule) -> RecurrenceRuleSchema:
        return cls.model_validate(recurrence_rule_to_mapping(rule))


# ── 回の鍵 ──────────────────────────────────────────────────────────────────


class OccurrenceKeySchema(BaseModel):
    """繰り返しの 1 回: 予定のタイムゾーンでの候補日 ＋ 系列の開始時刻。"""

    date: dt.date
    start_time: dt.time | None = None

    def to_key(self) -> OccurrenceKey:
        return OccurrenceKey(self.date, self.start_time)


class OccurrenceKeyResponse(BaseModel):
    date: dt.date
    start_time: str | None = Field(description="HH:MM")

    @classmethod
    def from_key(cls, key: OccurrenceKey) -> OccurrenceKeyResponse:
        return cls(
            date=key.date,
            start_time=format_wall_time(key.time) if key.time is not None else None,
        )


# ── 予定の入力 ──────────────────────────────────────────────────────────────


class _StartsAt(BaseModel):
    start: MinuteInstant = Field(description="開始の UTC 瞬間（繰り返しは先頭の回）")
    duration_minutes: int = Field(gt=0, le=MAX_DURATION_MINUTES)


class CalendarEventCreateRequest(_StartsAt):
    """予定を作る。``recurrence`` があれば繰り返し、無ければ単発。"""

    title: str = Field(min_length=1, max_length=TITLE_MAX)
    time_zone: str | None = Field(default=None, description="IANA 名。省くと利用者の設定")
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None
    recurrence: RecurrenceRuleSchema | None = None


class CalendarEventUpdateRequest(BaseModel):
    """詳細を置き換える。単発で ``start`` と ``duration_minutes`` があれば日時も移す。"""

    title: str = Field(min_length=1, max_length=TITLE_MAX)
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = None
    task_id: int | None = None
    start: MinuteInstant | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=MAX_DURATION_MINUTES)
    color_key: EventColorKey | None = Field(default=None, description="null は今の色のまま")
    expected_version: int | None = None


class SeriesUpdateRequest(BaseModel):
    """繰り返しの「すべて」を直す。``start`` を省くと先頭の回の瞬間は今のまま。"""

    title: str = Field(min_length=1, max_length=TITLE_MAX)
    duration_minutes: int = Field(gt=0, le=MAX_DURATION_MINUTES)
    recurrence: RecurrenceRuleSchema
    start: MinuteInstant | None = None
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = None
    task_id: int | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    expected_version: int | None = None


class FollowingOccurrencesChangeRequest(_StartsAt):
    """「この回以降」を直す: 元の系列をこの回の前日で終え、``start`` からの新しい系列を作る。

    ``task_id`` を省くと元の系列のタスクを引き継ぐ（``null`` を送ると外す）。
    """

    occurrence: OccurrenceKeySchema
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    recurrence: RecurrenceRuleSchema
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None
    expected_version: int | None = None


class ThisOccurrenceChangeRequest(_StartsAt):
    """「この回だけ」を直す: 系列からその回を飛ばし、単発を新しく作る。

    ``task_id`` を省くと系列のタスクを引き継ぐ（``null`` を送ると外す）。
    """

    occurrence: OccurrenceKeySchema
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None
    expected_version: int | None = None


class OccurrenceActionRequest(BaseModel):
    """回を 1 つ指す操作（飛ばす・戻す・移動の取り消し・以降を消す）。"""

    occurrence: OccurrenceKeySchema
    expected_version: int | None = None


class OccurrenceMoveRequest(_StartsAt):
    """その回だけ ``start`` へ移す。``title`` / ``location`` は null なら系列のまま。"""

    occurrence: OccurrenceKeySchema
    title: str | None = Field(default=None, max_length=TITLE_MAX)
    location: str | None = Field(default=None, max_length=TITLE_MAX)
    expected_version: int | None = None


# ── 予定の出力 ──────────────────────────────────────────────────────────────


class EventExceptionResponse(BaseModel):
    occurrence: OccurrenceKeyResponse
    type: str


class EventMoveResponse(BaseModel):
    occurrence: OccurrenceKeyResponse
    new_date: dt.date
    new_start_time: str | None
    new_duration_minutes: int | None
    title: str | None
    location: str | None


class CalendarEventResponse(BaseModel):
    id: int
    kind: Literal["SINGLE", "RECURRING"]
    title: str
    time_zone: str
    start: UtcDatetime = Field(description="単発の開始・繰り返しの先頭の回の UTC 瞬間")
    duration_minutes: int
    recurrence: RecurrenceRuleSchema | None
    location: str | None
    description: str | None
    color_key: EventColorKey
    task_id: int | None
    exceptions: list[EventExceptionResponse]
    moves: list[EventMoveResponse]
    version: int
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_event(cls, event: CalendarEvent) -> CalendarEventResponse:
        assert event.id is not None
        if event.single_schedule is not None:
            start = event.single_schedule.start_utc
            duration = event.single_schedule.duration_minutes
            recurrence = None
        else:
            assert event.recurring_schedule is not None
            start = event.recurring_schedule.anchor_utc
            duration = event.recurring_schedule.duration_minutes
            recurrence = RecurrenceRuleSchema.from_rule(event.recurring_schedule.recurrence_rule)
        return cls(
            id=event.id,
            kind=event.kind.value,
            title=event.title,
            time_zone=event.time_zone.name,
            start=start,
            duration_minutes=duration,
            recurrence=recurrence,
            location=event.location,
            description=event.description,
            color_key=event.color_key,
            task_id=event.task_id,
            exceptions=[
                EventExceptionResponse(
                    occurrence=OccurrenceKeyResponse.from_key(e.occurrence_key), type=e.type.value
                )
                for e in event.exceptions
            ],
            moves=[
                EventMoveResponse(
                    occurrence=OccurrenceKeyResponse.from_key(m.occurrence_key),
                    new_date=m.new_date,
                    new_start_time=(
                        format_wall_time(m.new_start_time) if m.new_start_time else None
                    ),
                    new_duration_minutes=m.new_duration_minutes,
                    title=m.title,
                    location=m.location,
                )
                for m in event.moves
            ],
            version=event.version,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


class CalendarOccurrenceResponse(BaseModel):
    """予定の 1 回（閲覧者のタイムゾーンへ投影済み）。

    時刻付きの回は ``start``（UTC 瞬間）＋ ``duration_minutes`` で置く。終日（ローカル 0:00 ＋
    1440 分）は「浮いた日」で、``date``（閲覧者のローカル日）にそのまま置く。
    """

    id: str = Field(description="回の識別子。単発は予定の id、繰り返しは `<event_id>:<日>T<時刻>`")
    event_id: int
    event_version: int = Field(description="回の操作で expected_version に渡す版")
    title: str
    start: UtcDatetime
    duration_minutes: int
    date: dt.date = Field(description="閲覧者のローカル日")
    start_time: str = Field(description="閲覧者のローカル時刻（HH:MM）")
    is_all_day: bool
    color_key: EventColorKey
    location: str | None
    task_id: int | None
    is_recurring: bool
    is_moved: bool
    is_overridden: bool
    series_key: OccurrenceKeyResponse | None = Field(
        description="繰り返しの元の鍵（予定のタイムゾーン）。単発は null"
    )

    @classmethod
    def from_view(cls, view: OccurrenceView) -> CalendarOccurrenceResponse:
        series_key = (
            OccurrenceKeyResponse.from_key(view.series_key) if view.series_key else None
        )
        occurrence_id = (
            f"{view.event_id}:{series_key.date.isoformat()}T{series_key.start_time or ''}"
            if series_key is not None
            else str(view.event_id)
        )
        return cls(
            id=occurrence_id,
            event_id=view.event_id,
            event_version=view.event_version,
            title=view.title,
            start=view.start_utc,
            duration_minutes=view.duration_minutes,
            date=view.date,
            start_time=format_wall_time(view.start_time),
            is_all_day=view.is_all_day,
            color_key=view.color_key,
            location=view.location,
            task_id=view.task_id,
            is_recurring=view.is_recurring,
            is_moved=view.is_moved,
            is_overridden=view.is_overridden,
            series_key=series_key,
        )


# ── 営業日カレンダー ────────────────────────────────────────────────────────


class HolidaySchema(BaseModel):
    date: dt.date
    name: str | None = Field(default=None, max_length=200)

    @classmethod
    def from_holiday(cls, holiday: Holiday) -> HolidaySchema:
        return cls(date=holiday.date, name=holiday.name)

    def to_holiday(self) -> Holiday:
        return Holiday(self.date, self.name)


class HolidaysBulkRequest(BaseModel):
    """祝日をまとめて足す。すでにある日はそのまま（名前も変えない）。"""

    holidays: list[HolidaySchema] = Field(max_length=1000)


class JapaneseHolidaysImportRequest(BaseModel):
    """その年の日本の祝日・振替休日・国民の休日を足す（暦から出す。2007〜2099 年）。"""

    year: int


class BusinessCalendarCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    time_zone: str | None = Field(default=None, description="IANA 名。省くと利用者の設定")
    workdays: list[Weekday] = Field(
        default_factory=lambda: [
            Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY,
        ]
    )
    shift_on_holidays_only: bool = False
    is_enabled: bool = True


class BusinessCalendarUpdateRequest(BaseModel):
    """名前・営業日・シフトの仕方・有効を置き換える（祝日は残す）。"""

    name: str = Field(min_length=1, max_length=200)
    workdays: list[Weekday]
    shift_on_holidays_only: bool = False
    is_enabled: bool = True


class BusinessCalendarResponse(BaseModel):
    id: int
    name: str
    time_zone: str
    workdays: list[Weekday]
    shift_on_holidays_only: bool
    is_enabled: bool
    holidays: list[HolidaySchema]
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_calendar(cls, calendar: BusinessCalendar) -> BusinessCalendarResponse:
        assert calendar.id is not None
        return cls(
            id=calendar.id,
            name=calendar.name,
            time_zone=calendar.time_zone.name,
            workdays=sorted(calendar.workdays, key=lambda w: w.iso_index),
            shift_on_holidays_only=calendar.shift_on_holidays_only,
            is_enabled=calendar.is_enabled,
            holidays=[
                HolidaySchema.from_holiday(h) for h in sorted(calendar.holidays, key=lambda h: h.date)
            ],
            created_at=calendar.created_at,
            updated_at=calendar.updated_at,
        )
