"""予定のカレンダー・表示の選択・表示の組み合わせの API スキーマ（task #191、ADR-0027）。

取り込んだカレンダー（task #196、ADR-0037）の作る・読み込み直す・回もここ。
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.application.dto.calendar_import_dto import (
    FeedSource,
    FileFeedSource,
    ImportedOccurrenceView,
    UrlFeedSource,
)
from src.domain.entities.calendar import (
    NAME_MAX_LENGTH,
    Calendar,
    CalendarKind,
    CalendarScope,
    DayOffReason,
)
from src.domain.entities.calendar_import import CalendarImport, ImportSource
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.entities.day_off import DayOff
from src.domain.services.day_off_layers import DayOffMark
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.recurrence import Weekday
from src.presentation.api.schemas.calendar_schemas import format_wall_time
from src.presentation.api.schemas.types import UtcDatetime

MAX_IDS = 500
SCOPE_DESCRIPTION = (
    "仕事 / プライベート（ADR-0033）。PRIVATE の予定は計画（予定した時間・締めの予定）と"
    "打刻の既定のタスクに数えず、タスクを結べない"
)


class CalendarCreateRequest(BaseModel):
    """カレンダーを作る。末尾に足し、最初から表示。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey = Field(
        default=EventColorKey.DEFAULT, description="色。DEFAULT は色の指定なし（予定は標準の色）"
    )
    scope: CalendarScope = Field(default=CalendarScope.WORK, description=SCOPE_DESCRIPTION)


class CalendarUpdateRequest(BaseModel):
    """名前と色を置き換える。休みの層は「休みとして数える」・稼働する曜日も（省けば今のまま）。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey
    counts_as_day_off: bool | None = Field(
        default=None, description="休みの日の一覧の層: 営業日の判定で休みとして数える"
    )
    workdays: list[Weekday] | None = Field(default=None, description="営業日の層: 稼働する曜日")
    scope: CalendarScope | None = Field(
        default=None,
        description="予定のカレンダー: 仕事 / プライベート（省けば今のまま）。既定のカレンダー・休みの層は"
        " PRIVATE にできない（422）。タスクを結んだ予定があれば 409",
    )


class CalendarOrderRequest(BaseModel):
    """この順に並べる（渡さなかったものはその後ろに今の順で）。"""

    calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarVisibilityRequest(BaseModel):
    """表示するカレンダーを、渡したものだけにする（ほかは隠す）。"""

    visible_calendar_ids: list[int] = Field(max_length=MAX_IDS)


class CalendarImportStatusResponse(BaseModel):
    """取り込んだカレンダーの読み込みの状態（ADR-0037）。⚠ URL そのものは返さない。"""

    source: ImportSource = Field(description="最後に読み込んだ入れ方（FILE / URL）")
    imported_at: UtcDatetime = Field(description="最後に読み込めた時刻")
    event_count: int = Field(description="持っている回の数（今日の前後の期間で展開したもの）")
    is_subscribed: bool = Field(description="URL を購読している（定期的に読み込み直す）")
    url_hint: str | None = Field(description="購読している URL の手掛かり（ホスト名と末尾だけ）")
    last_attempt_at: UtcDatetime | None = Field(description="最後に読み込みを試みた時刻")
    last_error: str | None = Field(
        description="最後の読み込みの失敗の理由（成功すれば null）。値は 422 の reason と同じ"
    )

    @classmethod
    def from_import(cls, calendar_import: CalendarImport) -> CalendarImportStatusResponse:
        subscription = calendar_import.subscription
        return cls(
            source=calendar_import.source,
            imported_at=calendar_import.imported_at,
            event_count=calendar_import.event_count,
            is_subscribed=subscription is not None,
            url_hint=subscription.url_hint if subscription else None,
            last_attempt_at=calendar_import.last_attempt_at,
            last_error=calendar_import.last_error,
        )


class CalendarResponse(BaseModel):
    id: int
    kind: CalendarKind = Field(
        description="種類。EVENTS = 予定を入れるカレンダー / WORKWEEK = 営業日の層 / DAYS_OFF = 休みの日の一覧の層"
        " / IMPORTED = 外の iCalendar を読み込んだカレンダー（読み取り専用）"
    )
    name: str
    color_key: EventColorKey
    sort_order: int
    is_default: bool = Field(description="既定のカレンダー（消せない。消したカレンダーの予定の行き先）")
    is_visible: bool = Field(description="カレンダーの画面に出す（サーバーに覚える）")
    workdays: list[Weekday] | None = Field(description="営業日の層の稼働する曜日（ほかは null）")
    day_off_reason: DayOffReason | None = Field(description="休みの日の一覧の層の理由（ほかは null）")
    counts_as_day_off: bool = Field(description="営業日の判定で休みとして数える（休みの日の一覧の層）")
    scope: CalendarScope = Field(description=SCOPE_DESCRIPTION)
    imported: CalendarImportStatusResponse | None = Field(
        default=None, description="取り込んだカレンダーの読み込みの状態（ほかは null）"
    )
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_calendar(
        cls, calendar: Calendar, calendar_import: CalendarImport | None = None
    ) -> CalendarResponse:
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
            scope=calendar.scope,
            imported=(
                CalendarImportStatusResponse.from_import(calendar_import)
                if calendar_import is not None
                else None
            ),
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


# ── 取り込んだカレンダー（ADR-0037）──────────────────────────────────────────

MAX_FEED_TEXT_LENGTH = 10 * 1024 * 1024
MAX_FEED_URL_LENGTH = 4000


class FeedSourceRequest(BaseModel):
    """読み込む中身。FILE はファイルの中身（テキスト）、URL は https（webcal）の URL。"""

    type: Literal["FILE", "URL"]
    content: str | None = Field(
        default=None, max_length=MAX_FEED_TEXT_LENGTH, description="FILE: .ics の中身"
    )
    url: str | None = Field(
        default=None, max_length=MAX_FEED_URL_LENGTH,
        description="URL: Google の「iCal 形式の非公開アドレス」・Outlook の公開 ICS など",
    )
    subscribe: bool = Field(
        default=False,
        description="URL: URL を覚えて 15 分ごとに読み込み直す。false なら 1 回読んで URL は保存しない",
    )

    @model_validator(mode="after")
    def _matches_type(self) -> FeedSourceRequest:
        if self.type == "FILE" and not self.content:
            raise ValueError("a FILE source needs content")
        if self.type == "URL" and not (self.url and self.url.strip()):
            raise ValueError("a URL source needs url")
        return self

    def to_source(self) -> FeedSource:
        if self.type == "FILE":
            assert self.content is not None
            return FileFeedSource(content=self.content.encode("utf-8"))
        assert self.url is not None
        return UrlFeedSource(url=self.url.strip(), subscribe=self.subscribe)


class ImportedCalendarCreateRequest(BaseModel):
    """取り込んだカレンダーを作る（読み込めなければ作らない）。末尾に足し、最初から表示。"""

    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    color_key: EventColorKey = Field(default=EventColorKey.DEFAULT)
    source: FeedSourceRequest


class CalendarImportSettingsResponse(BaseModel):
    subscription_available: bool = Field(
        description="URL を購読できる配備か（封じる鍵がある）。false でも 1 回だけの URL とファイルは使える"
    )
    refresh_interval_minutes: int = Field(description="購読を読み込み直す間隔（分）")


class ImportedOccurrenceResponse(BaseModel):
    """取り込んだ回（閲覧者のタイムゾーンへ直したもの。読み取り専用）。

    終日の回は日ごとに 1 つ。``id`` はこの応答の中だけで一意（読み込み直すと変わる）。
    """

    id: str
    calendar_id: int
    title: str
    location: str | None
    start: UtcDatetime
    duration_minutes: int
    date: dt.date = Field(description="閲覧者のローカル日")
    start_time: str = Field(description="閲覧者のローカル時刻（HH:MM）")
    is_all_day: bool
    calendar_color_key: EventColorKey

    @classmethod
    def from_view(cls, index: int, view: ImportedOccurrenceView) -> ImportedOccurrenceResponse:
        return cls(
            id=f"imported:{view.calendar_id}:{index}",
            calendar_id=view.calendar_id,
            title=view.title,
            location=view.location,
            start=view.start_utc,
            duration_minutes=view.duration_minutes,
            date=view.date,
            start_time=format_wall_time(view.start_time),
            is_all_day=view.is_all_day,
            calendar_color_key=view.calendar_color_key,
        )
