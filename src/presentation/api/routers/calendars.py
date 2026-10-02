"""予定のカレンダー・表示の選択・表示の組み合わせの API（task #191、ADR-0027）。

- ``/calendars``: 一覧（並び順。既定のカレンダーが無ければ作る）・作る・名前と色・消す
  （既定は 409。中の予定は既定へ移る）
- ``PUT /calendars/order``: 並べ替え
- ``PUT /calendars/visibility``: 表示するカレンダーをまとめて置き換える（サーバーに覚える）
- ``/calendar-view-presets``: 表示の組み合わせ。``POST .../{id}/apply`` で当てる

他人のカレンダー・組み合わせは 404。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from src.presentation.api.dependencies import CalendarUseCasesDep, CurrentUserDep
from src.presentation.api.schemas.calendar_set_schemas import (
    CalendarCreateRequest,
    CalendarDeleteResponse,
    CalendarOrderRequest,
    CalendarResponse,
    CalendarUpdateRequest,
    CalendarViewPresetRequest,
    CalendarViewPresetResponse,
    CalendarVisibilityRequest,
)

router = APIRouter(prefix="/calendars", tags=["calendars"])
presets_router = APIRouter(prefix="/calendar-view-presets", tags=["calendars"])


@router.get("", response_model=list[CalendarResponse])
def list_calendars(current_user: CurrentUserDep, calendars: CalendarUseCasesDep) -> list[CalendarResponse]:
    return [CalendarResponse.from_calendar(c) for c in calendars.list_calendars(current_user.user_id)]


@router.post("", response_model=CalendarResponse, status_code=status.HTTP_201_CREATED)
def create_calendar(
    body: CalendarCreateRequest, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> CalendarResponse:
    created = calendars.create_calendar(current_user.user_id, body.name, body.color_key)
    return CalendarResponse.from_calendar(created)


# ⚠ 固定の道（order / visibility）は ``/{calendar_id}`` より先に置く（後ろだと id として読まれて 422）。
@router.put("/order", response_model=list[CalendarResponse])
def reorder_calendars(
    body: CalendarOrderRequest, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> list[CalendarResponse]:
    return [
        CalendarResponse.from_calendar(c)
        for c in calendars.reorder_calendars(current_user.user_id, body.calendar_ids)
    ]


@router.put("/visibility", response_model=list[CalendarResponse])
def set_visible_calendars(
    body: CalendarVisibilityRequest, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> list[CalendarResponse]:
    """表示するカレンダーを、渡したものだけにする。「すべて」は全部の id を送る。"""
    return [
        CalendarResponse.from_calendar(c)
        for c in calendars.set_visible_calendars(current_user.user_id, body.visible_calendar_ids)
    ]


@router.put("/{calendar_id}", response_model=CalendarResponse)
def update_calendar(
    calendar_id: int,
    body: CalendarUpdateRequest,
    current_user: CurrentUserDep,
    calendars: CalendarUseCasesDep,
) -> CalendarResponse:
    updated = calendars.update_calendar(calendar_id, current_user.user_id, body.name, body.color_key)
    return CalendarResponse.from_calendar(updated)


@router.delete("/{calendar_id}", response_model=CalendarDeleteResponse)
def delete_calendar(
    calendar_id: int, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> CalendarDeleteResponse:
    """消す。中の予定は既定のカレンダーへ移る。既定のカレンダーは消せない（409）。"""
    moved = calendars.delete_calendar(calendar_id, current_user.user_id)
    return CalendarDeleteResponse(moved_event_count=moved)


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
    preset_id: int, current_user: CurrentUserDep, calendars: CalendarUseCasesDep
) -> list[CalendarResponse]:
    """組み合わせを当てる: 入っているカレンダーだけを表示にする。表示の状態の一覧を返す。"""
    return [
        CalendarResponse.from_calendar(c)
        for c in calendars.apply_preset(preset_id, current_user.user_id)
    ]
