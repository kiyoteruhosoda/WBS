"""予定のカレンダー・表示の選択・表示の組み合わせの API（task #191、ADR-0027）。

- ``/calendars``: 一覧（並び順。既定のカレンダーが無ければ作る）・作る・名前と色・消す
  （既定は 409。中の予定は既定へ移る）
- ``PUT /calendars/order``: 並べ替え
- ``PUT /calendars/visibility``: 表示するカレンダーをまとめて置き換える（サーバーに覚える）
- ``/calendar-view-presets``: 表示の組み合わせ。``POST .../{id}/apply`` で当てる
- 休みの層（ADR-0029）: ``GET /calendars/days-off``（期間の休みの理由）・
  ``/calendars/{id}/days-off``（日付の一覧の層の日を引く・足す・消す・``/japan`` で日本の祝日を年ごとに）

取り込んだカレンダー（task #196、ADR-0037。外の iCalendar を読み取り専用で持つ）:

- ``GET /calendars/import-settings``: 購読できる配備か・読み込み直す間隔
- ``POST /calendars/imported``: ファイルか URL を読んで作る（読めなければ作らない）
- ``POST /calendars/{id}/import``: 新しいファイル・URL で入れ替える（購読はこの入れ方のものに置き換わる）
- ``POST /calendars/{id}/refresh``: 購読している URL を今すぐ読み込み直す
- ``DELETE /calendars/{id}/subscription``: 購読をやめる（URL を忘れる。回は残す）
- ``GET /calendars/imported-occurrences``: 期間の取り込んだ回（閲覧者のタイムゾーン）

読み込めないときは 422 で ``reason``（``invalid_url`` / ``blocked_address`` / ``unreachable`` /
``not_found`` / ``forbidden`` / ``http_error`` / ``too_large`` / ``not_icalendar`` / ``too_many_events`` /
``subscription_unavailable``）。

他人のカレンダー・組み合わせは 404。
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.application.use_cases.calendar_import_use_cases import (
    SUBSCRIPTION_INTERVAL,
    CalendarImportUseCases,
)
from src.domain.entities.calendar import Calendar
from src.presentation.api.dependencies import (
    CalendarImportUseCasesDep,
    CalendarUseCasesDep,
    CurrentUserDep,
    DayOffUseCasesDep,
)
from src.presentation.api.schemas.calendar_set_schemas import (
    CalendarCreateRequest,
    CalendarDeleteResponse,
    CalendarImportSettingsResponse,
    CalendarImportStatusResponse,
    CalendarOrderRequest,
    CalendarResponse,
    CalendarUpdateRequest,
    CalendarViewPresetRequest,
    CalendarViewPresetResponse,
    CalendarVisibilityRequest,
    DayOffMarkResponse,
    DayOffRequest,
    DayOffResponse,
    FeedSourceRequest,
    ImportedCalendarCreateRequest,
    ImportedOccurrenceResponse,
    JapaneseHolidaysRequest,
)

router = APIRouter(prefix="/calendars", tags=["calendars"])
presets_router = APIRouter(prefix="/calendar-view-presets", tags=["calendars"])


def _responses(
    listed: list[Calendar], user_id: int, imports: CalendarImportUseCases
) -> list[CalendarResponse]:
    """一覧の応答。取り込んだカレンダーには読み込みの状態を添える。"""
    states = imports.imports_of(user_id) if any(c.is_imported for c in listed) else {}
    return [CalendarResponse.from_calendar(c, states.get(c.id or 0)) for c in listed]


@router.get("", response_model=list[CalendarResponse])
def list_calendars(
    current_user: CurrentUserDep, calendars: CalendarUseCasesDep, imports: CalendarImportUseCasesDep
) -> list[CalendarResponse]:
    return _responses(
        calendars.list_calendars(current_user.user_id), current_user.user_id, imports
    )


@router.post("", response_model=CalendarResponse, status_code=status.HTTP_201_CREATED)
def create_calendar(
    body: CalendarCreateRequest, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> CalendarResponse:
    created = calendars.create_calendar(
        current_user.user_id, body.name, body.color_key, body.scope
    )
    return CalendarResponse.from_calendar(created)


# ⚠ 固定の道（order / visibility）は ``/{calendar_id}`` より先に置く（後ろだと id として読まれて 422）。
@router.put("/order", response_model=list[CalendarResponse])
def reorder_calendars(
    body: CalendarOrderRequest,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
    imports: CalendarImportUseCasesDep,
) -> list[CalendarResponse]:
    return _responses(
        calendars.reorder_calendars(current_user.user_id, body.calendar_ids),
        current_user.user_id, imports,
    )


@router.put("/visibility", response_model=list[CalendarResponse])
def set_visible_calendars(
    body: CalendarVisibilityRequest,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
    imports: CalendarImportUseCasesDep,
) -> list[CalendarResponse]:
    """表示するカレンダーを、渡したものだけにする。「すべて」は全部の id を送る。"""
    return _responses(
        calendars.set_visible_calendars(current_user.user_id, body.visible_calendar_ids),
        current_user.user_id, imports,
    )


@router.get("/import-settings", response_model=CalendarImportSettingsResponse)
def import_settings(
    current_user: CurrentUserDep, imports: CalendarImportUseCasesDep
) -> CalendarImportSettingsResponse:
    return CalendarImportSettingsResponse(
        subscription_available=imports.subscription_available,
        refresh_interval_minutes=int(SUBSCRIPTION_INTERVAL.total_seconds() // 60),
    )


@router.post("/imported", response_model=CalendarResponse, status_code=status.HTTP_201_CREATED)
def create_imported_calendar(
    body: ImportedCalendarCreateRequest,
    current_user: CurrentUserDep,
    imports: CalendarImportUseCasesDep,
) -> CalendarResponse:
    """ファイルか URL を読んで、取り込んだカレンダーを作る。読めなければ 422（何も作らない）。"""
    calendar, calendar_import = imports.create_imported_calendar(
        current_user.user_id, body.name, body.color_key, body.source.to_source()
    )
    return CalendarResponse.from_calendar(calendar, calendar_import)


FromDate = Annotated[dt.date, Query(alias="from", description="期間の初日（含む）")]
ToDate = Annotated[dt.date, Query(alias="to", description="期間の末日（含む）")]
OptionalFrom = Annotated[dt.date | None, Query(alias="from", description="期間の初日（含む）")]
OptionalTo = Annotated[dt.date | None, Query(alias="to", description="期間の末日（含む）")]


@router.get("/days-off", response_model=list[DayOffMarkResponse])
def list_day_off_marks(
    from_date: FromDate, to_date: ToDate, current_user: CurrentUserDep, days_off: DayOffUseCasesDep
) -> list[DayOffMarkResponse]:
    """期間の休みの理由（日付の順）。曜日の休み（営業日の層に当たらない日）と、日付の一覧の層の日。

    営業日 = どの ``counts_as_day_off`` の理由も無い日。表示の選択には関係しない（塗るかどうかは画面が
    ``calendar_id`` の表示で決める）。期間は 800 日まで。
    """
    return [
        DayOffMarkResponse.from_mark(m)
        for m in days_off.marks(current_user.user_id, from_date, to_date)
    ]


@router.get("/imported-occurrences", response_model=list[ImportedOccurrenceResponse])
def list_imported_occurrences(
    from_date: FromDate,
    to_date: ToDate,
    current_user: CurrentUserDep,
    imports: CalendarImportUseCasesDep,
    time_zone: Annotated[
        str | None, Query(description="閲覧者のタイムゾーン（IANA 名）。省くと利用者の設定")
    ] = None,
) -> list[ImportedOccurrenceResponse]:
    """期間の取り込んだ回（日付・開始時刻の順。表示の選択に関係なく全部）。期間は 800 日まで。

    予定の回（``/calendar/occurrences``）とは別に返す（計画・締め・打刻には入らない）。
    """
    views = imports.list_occurrence_views(
        current_user.user_id, from_date, to_date, time_zone or current_user.timezone
    )
    return [ImportedOccurrenceResponse.from_view(i, v) for i, v in enumerate(views)]


@router.put("/{calendar_id}", response_model=CalendarResponse)
def update_calendar(
    calendar_id: int,
    body: CalendarUpdateRequest,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
    imports: CalendarImportUseCasesDep,
) -> CalendarResponse:
    updated = calendars.update_calendar(
        calendar_id, current_user.user_id, body.name, body.color_key,
        counts_as_day_off=body.counts_as_day_off,
        workdays=frozenset(body.workdays) if body.workdays is not None else None,
        scope=body.scope,
    )
    return _responses([updated], current_user.user_id, imports)[0]


@router.post("/{calendar_id}/import", response_model=CalendarImportStatusResponse)
def reimport_calendar(
    calendar_id: int,
    body: FeedSourceRequest,
    current_user: CurrentUserDep,
    imports: CalendarImportUseCasesDep,
) -> CalendarImportStatusResponse:
    """新しいファイル・URL で回を入れ替える。購読はこの入れ方のものに置き換わる
    （ファイル・購読しない URL なら購読をやめる）。読めなければ 422（中身は前のまま）。"""
    return CalendarImportStatusResponse.from_import(
        imports.reimport(calendar_id, current_user.user_id, body.to_source())
    )


@router.post("/{calendar_id}/refresh", response_model=CalendarImportStatusResponse)
def refresh_calendar(
    calendar_id: int, current_user: CurrentUserDep, imports: CalendarImportUseCasesDep
) -> CalendarImportStatusResponse:
    """購読している URL を今すぐ読み込み直す。購読していなければ 409。読めなければ 422（理由は覚える）。"""
    return CalendarImportStatusResponse.from_import(
        imports.refresh(calendar_id, current_user.user_id)
    )


@router.delete("/{calendar_id}/subscription", response_model=CalendarImportStatusResponse)
def unsubscribe_calendar(
    calendar_id: int, current_user: CurrentUserDep, imports: CalendarImportUseCasesDep
) -> CalendarImportStatusResponse:
    """購読をやめる（URL を忘れる。読み込んだ回は残す）。"""
    return CalendarImportStatusResponse.from_import(
        imports.unsubscribe(calendar_id, current_user.user_id)
    )


@router.delete("/{calendar_id}", response_model=CalendarDeleteResponse)
def delete_calendar(
    calendar_id: int, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> CalendarDeleteResponse:
    """消す。中の予定は既定のカレンダーへ移る。既定のカレンダーは消せない（409）。"""
    moved = calendars.delete_calendar(calendar_id, current_user.user_id)
    return CalendarDeleteResponse(moved_event_count=moved)


@router.get("/{calendar_id}/days-off", response_model=list[DayOffResponse])
def list_days_off(
    calendar_id: int,
    current_user: CurrentUserDep,
    days_off: DayOffUseCasesDep,
    from_date: OptionalFrom = None,
    to_date: OptionalTo = None,
) -> list[DayOffResponse]:
    """休みの日の一覧の層の日（日付の順）。"""
    return [
        DayOffResponse.from_day_off(d)
        for d in days_off.list_days(calendar_id, current_user.user_id, from_date, to_date)
    ]


@router.post("/{calendar_id}/days-off", response_model=list[DayOffResponse])
def add_day_off(
    calendar_id: int, body: DayOffRequest, current_user: CurrentUserDep, days_off: DayOffUseCasesDep
) -> list[DayOffResponse]:
    """1 日足す（同じ日があれば何もしない）。その年の日を返す。"""
    return [
        DayOffResponse.from_day_off(d)
        for d in days_off.add_day(calendar_id, current_user.user_id, body.date, body.name)
    ]


@router.delete("/{calendar_id}/days-off/{day}", response_model=list[DayOffResponse])
def remove_day_off(
    calendar_id: int, day: dt.date, current_user: CurrentUserDep, days_off: DayOffUseCasesDep
) -> list[DayOffResponse]:
    return [
        DayOffResponse.from_day_off(d)
        for d in days_off.remove_day(calendar_id, current_user.user_id, day)
    ]


@router.post("/{calendar_id}/days-off/japan", response_model=list[DayOffResponse])
def import_japanese_holidays(
    calendar_id: int,
    body: JapaneseHolidaysRequest,
    current_user: CurrentUserDep,
    days_off: DayOffUseCasesDep,
) -> list[DayOffResponse]:
    """その年の日本の祝日・振替休日・国民の休日を足す（2007〜2099 年）。その年の日を返す。"""
    return [
        DayOffResponse.from_day_off(d)
        for d in days_off.import_japanese_holidays(calendar_id, current_user.user_id, body.year)
    ]


# ── 表示の組み合わせ ────────────────────────────────────────────────────────


@presets_router.get("", response_model=list[CalendarViewPresetResponse])
def list_presets(
    current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> list[CalendarViewPresetResponse]:
    return [
        CalendarViewPresetResponse.from_preset(p)
        for p in calendars.list_presets(current_user.user_id)
    ]


@presets_router.post(
    "", response_model=CalendarViewPresetResponse, status_code=status.HTTP_201_CREATED
)
def create_preset(
    body: CalendarViewPresetRequest, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> CalendarViewPresetResponse:
    created = calendars.create_preset(current_user.user_id, body.name, body.calendar_ids)
    return CalendarViewPresetResponse.from_preset(created)


@presets_router.put("/{preset_id}", response_model=CalendarViewPresetResponse)
def update_preset(
    preset_id: int,
    body: CalendarViewPresetRequest,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
) -> CalendarViewPresetResponse:
    updated = calendars.update_preset(
        preset_id, current_user.user_id, body.name, body.calendar_ids
    )
    return CalendarViewPresetResponse.from_preset(updated)


@presets_router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(preset_id: int, current_user: CurrentUserDep, calendars: CalendarUseCasesDep) -> None:
    calendars.delete_preset(preset_id, current_user.user_id)


@presets_router.post("/{preset_id}/apply", response_model=list[CalendarResponse])
def apply_preset(
    preset_id: int,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
    imports: CalendarImportUseCasesDep,
) -> list[CalendarResponse]:
    """組み合わせを当てる: 入っているカレンダーだけを表示にする。表示の状態の一覧を返す。"""
    return _responses(
        calendars.apply_preset(preset_id, current_user.user_id), current_user.user_id, imports
    )
