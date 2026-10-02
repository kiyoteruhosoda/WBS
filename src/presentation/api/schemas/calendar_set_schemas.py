"""予定のカレンダー・表示の選択・表示の組み合わせの API スキーマ（task #191、ADR-0027）。"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from src.domain.entities.calendar import NAME_MAX_LENGTH, Calendar, CalendarKind, DayOffReason
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.entities.day_off import DayOff
from src.domain.services.day_off_layers import DayOffMark
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.recurrence import Weekday
from src.presentation.api.schemas.types import UtcDatetime

MAX_IDS = 500


class CalendarCreateRequest(BaseModel):
    """カレンダーを作る。末尾に足し、最初から表示。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey = Field(
        default=EventColorKey.DEFAULT, description="色。DEFAULT は色の指定なし（予定は標準の色）"
    )


class CalendarUpdateRequest(BaseModel):
    """名前と色を置き換える。休みの層は「休みとして数える」・稼働する曜日も（省けば今のまま）。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey
    counts_as_day_off: bool | None = Field(
        default=None, description="休みの日の一覧の層: 営業日の判定で休みとして数える"
    )
    workdays: list[Weekday] | None = Field(default=None, description="営業日の層: 稼働する曜日")


class CalendarOrderRequest(BaseModel):
    """この順に並べる（渡さなかったものはその後ろに今の順で）。"""

    calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarVisibilityRequest(BaseModel):
    """表示するカレンダーを、渡したものだけにする（ほかは隠す）。"""

    visible_calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarResponse(BaseModel):
    id: int
    kind: CalendarKind = Field(
        description="種類。EVENTS = 予定を入れるカレンダー / WORKWEEK = 営業日の層 / DAYS_OFF = 休みの日の一覧の層"
    )
    name: str
    color_key: EventColorKey
    sort_order: int
    is_default: bool = Field(description="既定のカレンダー（消せない。消したカレンダーの予定の行き先）")
    is_visible: bool = Field(description="カレンダーの画面に出す（サーバーに覚える）")
    workdays: list[Weekday] | None = Field(description="営業日の層の稼働する曜日（ほかは null）")
    day_off_reason: DayOffReason | None = Field(description="休みの日の一覧の層の理由（ほかは null）")
    counts_as_day_off: bool = Field(description="営業日の判定で休みとして数える（休みの日の一覧の層）")
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_calendar(cls, calendar: Calendar) -> CalendarResponse:
        assert calendar.id is not None
        return cls(
            id=calendar.id,
            kind=calendar.kind,
            name=calendar.name,
            color_key=calendar.color_key,
            sort_order=calendar.sort_order,
            is_default=calendar.is_default,
            is_visible=calendar.is_visible,
            workdays=(
                sorted(calendar.workdays, key=lambda w: w.iso_index)
                if calendar.workdays is not None
                else None
            ),
            day_off_reason=calendar.day_off_reason,
            counts_as_day_off=calendar.counts_as_day_off,
            created_at=calendar.created_at,
            updated_at=calendar.updated_at,
        )


class CalendarDeleteResponse(BaseModel):
    moved_event_count: int = Field(description="既定のカレンダーへ移した予定の数")


class CalendarViewPresetRequest(BaseModel):
    """表示の組み合わせ（名前 ＋ 表示にするカレンダー）。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarViewPresetResponse(BaseModel):
    id: int
    name: str
    calendar_ids: list[int] = Field(description="当てると表示になるカレンダー（ほかは隠れる）")
    sort_order: int
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_preset(cls, preset: CalendarViewPreset) -> CalendarViewPresetResponse:
        assert preset.id is not None
        return cls(
            id=preset.id,
            name=preset.name,
            calendar_ids=list(preset.calendar_ids),
            sort_order=preset.sort_order,
            created_at=preset.created_at,
            updated_at=preset.updated_at,
        )


# ── 休みの層（ADR-0029）──────────────────────────────────────────────────────


class DayOffRequest(BaseModel):
    date: dt.date
    name: str | None = Field(default=None, max_length=200)


class DayOffResponse(BaseModel):
    date: dt.date
    name: str | None

    @classmethod
    def from_day_off(cls, day_off: DayOff) -> DayOffResponse:
        return cls(date=day_off.day, name=day_off.name)


class JapaneseHolidaysRequest(BaseModel):
    """その年の日本の祝日・振替休日・国民の休日を足す（暦から出す。2007〜2099 年）。"""

    year: int


class DayOffMarkResponse(BaseModel):
    """ある日が休みである理由 1 つ。"""

    date: dt.date
    reason: str = Field(
        description="WEEKLY = 曜日の休み / NATIONAL_HOLIDAY = 日本の祝日 / COMPANY = 会社の公休 / PERSONAL = 私の休み"
    )
    calendar_id: int | None = Field(description="理由の層（表示の選択で塗るかを決める）")
    name: str | None = Field(description="祝日名など（無ければ null）")
    counts_as_day_off: bool = Field(
        description="営業日の判定で休みとして数える（false の層の日は塗るが営業日のまま）"
    )

    @classmethod
    def from_mark(cls, mark: DayOffMark) -> DayOffMarkResponse:
        return cls(
            date=mark.day,
            reason=mark.reason,
            calendar_id=mark.calendar_id,
            name=mark.name,
            counts_as_day_off=mark.counts_as_day_off,
        )

