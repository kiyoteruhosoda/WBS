"""予定のカレンダー・表示の選択・表示の組み合わせの API スキーマ（task #191、ADR-0027）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.entities.calendar import NAME_MAX_LENGTH, Calendar, CalendarKind
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.value_objects.event_color import EventColorKey
from src.presentation.api.schemas.types import UtcDatetime

MAX_IDS = 500


class CalendarCreateRequest(BaseModel):
    """カレンダーを作る。末尾に足し、最初から表示。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey = Field(
        default=EventColorKey.DEFAULT, description="色。DEFAULT は色の指定なし（予定は標準の色）"
    )


class CalendarUpdateRequest(BaseModel):
    """名前と色を置き換える。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey


class CalendarOrderRequest(BaseModel):
    """この順に並べる（渡さなかったものはその後ろに今の順で）。"""

    calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarVisibilityRequest(BaseModel):
    """表示するカレンダーを、渡したものだけにする（ほかは隠す）。"""

    visible_calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarResponse(BaseModel):
    id: int
    kind: CalendarKind = Field(description="種類。EVENTS = 予定を入れるカレンダー")
    name: str
    color_key: EventColorKey
    sort_order: int
    is_default: bool = Field(description="既定のカレンダー（消せない。消したカレンダーの予定の行き先）")
    is_visible: bool = Field(description="カレンダーの画面に出す（サーバーに覚える）")
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
